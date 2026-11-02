"""Regression coverage for state equivalence, conflicting actions and API recovery."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import app
from checker import readings, simulator


def rule(event, conditions, action):
    return {"when": [event], "if": conditions, "device": "hallway_light", "do": action}


class RuleRobustness(unittest.TestCase):
    def test_equivalence_checks_initial_light_state(self):
        first = {"id": "R1", "rules": [rule("arrive", ["dark"], "on")]}
        second = {"id": "R2", "rules": first["rules"] + [rule("sunset", ["home"], "off")]}
        kept, merged = simulator.distinct([first, second], app.SCENARIOS)
        self.assertEqual(len(kept), 2)
        self.assertEqual(merged, [])

    def test_conflicting_actions_are_unusable(self):
        payload = {"unsupported": "", "readings": [{"label": "conflict", "rules": [
            rule("arrive", ["dark"], "on"), rule("arrive", ["dark"], "off")]}]}
        generated = readings.interpret("x", json.dumps(payload), {}, {})
        self.assertEqual(generated.error, "unusable")
        self.assertIn("conflicting", generated.error_detail)

    def test_opposite_actions_on_distinct_conditions_are_valid(self):
        reading = {"rules": [rule("arrive", ["dark"], "on"), rule("leave", [], "off")]}
        self.assertFalse(simulator.conflicts(reading))


class ApiRecovery(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.patches = [patch.object(app, "LOG", root / "sessions.jsonl"),
                        patch.object(app, "SAVED", root / "saved.json"),
                        patch.object(app, "MODE", "fixed"), patch.object(app, "SESSIONS", {})]
        for p in self.patches: p.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        for p in reversed(self.patches): p.stop()
        self.folder.cleanup()

    def request(self, path, body=None):
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_invalid_json_shape_returns_400(self):
        self.assertEqual(self.request("/api/start", [])[0], 400)
        self.assertEqual(self.request("/api/start", {"request": 42})[0], 400)

    def test_revisit_api_restores_answer_and_checks_input(self):
        _, view = self.request("/api/start", {"request": "When I arrive home after sunset, turn on the hallway light, and turn it off when I leave."})
        sid = view["session"]
        self.request("/api/answer", {"session": sid, "answer": "no"})
        self.assertEqual(self.request("/api/revisit", {"session": sid, "scenario": []})[0], 400)
        self.assertEqual(self.request("/api/revisit", {"session": sid, "scenario": "S4"})[0], 409)
        status, restored = self.request("/api/revisit", {"session": sid, "scenario": "S1", "action_id": "revisit-1"})
        self.assertEqual((status, restored["stage"], restored["history"]), (200, "question", []))
        self.assertEqual(self.request("/api/revisit", {"session": sid, "scenario": "S1", "action_id": "revisit-1"})[1], restored)

    def test_replay_and_session_recovery_do_not_repeat_save(self):
        _, view = self.request("/api/start", {"request": "When I arrive home after sunset, turn on the hallway light, and turn it off when I leave."})
        sid = view["session"]
        answer = {"session": sid, "answer": "no", "action_id": "answer-1"}
        _, first = self.request("/api/answer", answer)
        _, replay = self.request("/api/answer", answer)
        self.assertEqual(first, replay)
        self.assertEqual(first["stage"], "confirm")
        self.assertEqual(self.request("/api/session?session=" + sid)[1], first)
        self.assertEqual(self.request("/api/answer", {**answer, "answer": "yes"})[0], 409)
        save = {"session": sid, "choice": "save", "action_id": "save-1"}
        self.assertEqual(self.request("/api/decide", save)[1]["stage"], "saved")
        self.assertEqual(self.request("/api/decide", save)[1]["stage"], "saved")
        self.assertEqual(len(json.loads(app.SAVED.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__": unittest.main()
