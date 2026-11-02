"""Tests for the reading generator. No network: the model call is replaced where needed."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from checker import readings

FAKE_KEY = "TEST-ONLY-NOT-A-REAL-KEY"
REPLY = json.dumps({"unsupported": "", "readings": [
    {"label": "on when arriving after dark", "rules": [{"when": ["arrive"], "if": ["dark"], "device": "hallway_light", "do": "on"}]}]})


class Readings(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(readings.normalise("  Turn on the hallway light when I’m home   after dark. "),
                         "turn on the hallway light when i'm home after dark")

    def test_load_env_reads_bom_and_quotes_without_overriding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text('﻿# comment\nIIS_TEST_A="from file"\nIIS_TEST_B=from file\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"IIS_TEST_B": "already set"}):
                readings.load_env(path)
                self.assertEqual(os.environ["IIS_TEST_A"], "from file")
                self.assertEqual(os.environ["IIS_TEST_B"], "already set")
            os.environ.pop("IIS_TEST_A", None)

    def test_reply_text_skips_thoughts_and_rejects_empty(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": REPLY}]}}]}
        self.assertEqual(readings.reply_text(payload), REPLY)
        with self.assertRaises(readings.GeneratorError):
            readings.reply_text({"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]})

    def test_interpret(self):
        good = readings.interpret("x", REPLY, {}, {})
        self.assertEqual((good.error, len(good.readings)), ("", 1))
        self.assertEqual(readings.interpret("x", "not json", {}, {}).error, "unusable")
        self.assertEqual(readings.interpret("x", '{"unsupported": "", "readings": []}', {}, {}).error, "unusable")
        declined = readings.interpret("x", '{"unsupported": "a door lock", "readings": []}', {}, {})
        self.assertEqual((declined.error, declined.unsupported), ("", ["a door lock"]))

    def test_fixed_readings_are_labelled_simulated(self):
        generated = readings.generate("Turn on the hallway light when I'm home after dark.", mode="fixed")
        self.assertEqual(generated.source["kind"], "fixed")
        self.assertEqual(len(generated.readings), 2)

    def test_no_key_and_no_recording_is_an_honest_error(self):
        with mock.patch.object(readings, "api_key", return_value=""), \
             mock.patch.object(readings, "find_recording", return_value=None):
            generated = readings.generate("Turn on the hallway light at noon.")
        self.assertEqual(generated.error, "no_source")
        self.assertEqual(generated.readings, [])

    def test_key_goes_to_the_call_but_never_into_the_log(self):
        seen = {}

        def fake_call(context, endpoint, model, key, timeout=0):
            seen["key"] = key
            return REPLY, {"model_version": "test"}

        with mock.patch.object(readings, "api_key", return_value=FAKE_KEY), \
             mock.patch.object(readings, "find_recording", return_value=None), \
             mock.patch.object(readings, "call", side_effect=fake_call):
            generated = readings.generate("Turn on the hallway light when I arrive after dark.")
        self.assertEqual(seen["key"], FAKE_KEY)
        self.assertEqual(generated.source["kind"], "live")
        self.assertNotIn(FAKE_KEY, json.dumps(generated.to_log()))

    def test_context_sends_only_instruction_and_request(self):
        context = readings.build_context("Turn on the hallway light when I arrive home.")
        self.assertEqual(set(context), {"prompt_version", "instruction", "request"})
        self.assertTrue(context["request"].startswith('Request: "'))


if __name__ == "__main__":
    unittest.main()
