"""Tests for one request's flow: questions, repair, restatement, saving and the initiative rule."""
import json
import unittest
from pathlib import Path

from checker import readings
from checker.session import Session

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
A = "When I arrive home after sunset, turn on the hallway light, and turn it off when I leave."
B = "Turn on the hallway light when I'm home after dark."
OFF_RULE = "When you leave home: turn off the hallway light."


def start(text, **options):
    events = []
    session = Session(readings.generate(text, mode="fixed"), SCENARIOS, logger=events.append, **options)
    return session, events


class Flow(unittest.TestCase):
    def test_test_b_asks_where_readings_differ_then_probes_and_repairs(self):
        s, events = start(B)
        card = s.view()["card"]
        self.assertEqual((card["kind"], card["number"], s.pending["scenario"]["id"]), ("question", 1, "S1"))
        self.assertIn("2 rules", card["why"])
        s.answer("yes")
        card = s.view()["card"]
        self.assertEqual((s.pending["scenario"]["id"], card["number"]), ("S4", 2))
        self.assertIn("never off", card["why"])
        s.answer("yes")
        self.assertEqual(s.view()["card"], {"kind": "repair", "rule": OFF_RULE, "options": [
            ["add", "Add this rule"], ["dont_add", "Don't add"], ["edit", "Edit my request"]]})
        s.choose_repair("add")
        card = s.view()["card"]
        self.assertEqual(card["kind"], "confirm")
        self.assertEqual(card["rules"][1], OFF_RULE)
        self.assertEqual(card["never"], [])
        self.assertEqual(len(card["confirmed"]), 2)
        saved = []
        s.decide("save", store=saved.append)
        s.decide("save", store=saved.append)
        self.assertEqual((s.stage, len(saved)), ("saved", 1))
        self.assertEqual([e["event"] for e in events], [
            "start", "readings", "question", "answer", "question", "answer", "repair_offered", "repair_choice",
            "result", "decision"])

    def test_nothing_is_saved_without_save(self):
        s, _ = start(A)
        s.answer("no")
        self.assertEqual((s.stage, s.saved), ("confirm", None))
        s.decide("edit")
        self.assertEqual((s.stage, s.saved), ("edit", None))

    def test_clear_request_costs_one_probe_question(self):
        s, _ = start(A)
        self.assertEqual((s.pending["scenario"]["id"], s.pending["reason"]), ("S1", "flipped_trigger"))
        self.assertIn("already home", s.view()["card"]["why"])
        s.answer("no")
        self.assertEqual(s.stage, "confirm")

    def test_not_sure_keeps_both_readings_and_ends_with_a_choice(self):
        s, _ = start(B)
        s.answer("not_sure")
        self.assertEqual(s.pending["scenario"]["id"], "S4")
        s.answer("yes")
        s.choose_repair("add")
        card = s.view()["card"]
        self.assertEqual(card["kind"], "choose")
        self.assertEqual([d["id"] for d in card["differences"]], ["S1"])
        s.decide("use:R2+off")
        self.assertIn("it gets dark", s.saved["rule_text"])

    def test_dont_add_is_respected_and_the_gap_is_stated(self):
        s, _ = start(B)
        s.answer("yes")
        s.answer("yes")
        s.choose_repair("dont_add")
        view = s.view()
        self.assertEqual(view["card"]["never"], ["It never turns the light off."])
        self.assertEqual(view["card"]["mismatches"], 1)
        self.assertIn("light on, leave at 23:30: light on (differs: you said it should be off)", view["card"]["confirmed"])
        self.assertEqual(view["history"][1]["note"], "Not added: " + OFF_RULE)

    def test_declined_and_error_create_no_rule(self):
        declined = Session(readings.Generated("Lock the front door when I leave.", {"kind": "test"}, {},
                                              unsupported=["device 'front_door_lock'"]), SCENARIOS)
        self.assertEqual((declined.stage, declined.view()["card"]["needs"]), ("declined", ["device 'front_door_lock'"]))
        failed = Session(readings.Generated("x", {"kind": "live"}, {}, error="model_failed", error_detail="HTTP 503"),
                         SCENARIOS)
        card = failed.view()["card"]
        self.assertEqual((failed.stage, card["detail"], card["options"][0][0]), ("error", "HTTP 503", "retry"))
        self.assertEqual(failed.remaining, [])

    def test_back_restores_question_and_discards_later_repair(self):
        s, _ = start(B)
        s.answer("yes")
        s.answer("yes")
        self.assertEqual(s.stage, "repair")
        s.choose_repair("add")
        self.assertEqual(s.stage, "confirm")
        s.back()
        self.assertEqual(s.stage, "repair")
        s.back()
        self.assertEqual((s.stage, s.pending["scenario"]["id"]), ("question", "S4"))
        self.assertEqual(len(s.steps), 1)
        s.answer("no")
        self.assertEqual(s.stage, "confirm")
        self.assertEqual(len(s.remaining[0]["rules"]), 1)
        s.back()
        s.back()
        self.assertEqual((s.stage, s.pending["scenario"]["id"], len(s.steps)), ("question", "S1", 0))
        with self.assertRaises(ValueError):
            s.back()

    def test_revisit_keeps_later_answers_and_reapplies_same_repair(self):
        s, _ = start(B)
        s.answer("yes")
        s.answer("yes")
        s.choose_repair("add")
        s.revisit("S1")
        self.assertEqual((s.stage, s.pending["scenario"]["id"], len(s.steps)), ("question", "S1", 0))
        s.answer("no")
        self.assertEqual(s.stage, "confirm")
        self.assertEqual([(x["scenario"], x["answer"]) for x in s.steps], [("S1", "no"), ("S4", "yes")])
        self.assertTrue(s.steps[1]["restored"])
        self.assertIn("added", s.steps[1])
        self.assertEqual(s.view()["card"]["mismatches"], 0)

    def test_back_multiple_steps_keeps_later_answer_and_repair(self):
        s, _ = start(B)
        s.answer("yes")
        s.answer("yes")
        s.choose_repair("add")
        s.back()  # repair choice
        s.back()  # second question
        s.back()  # first question
        self.assertEqual(s.pending["scenario"]["id"], "S1")
        self.assertEqual(s.view()["retained"][0]["answer"], "Yes")
        s.answer("no")
        self.assertEqual(s.stage, "confirm")
        self.assertEqual(s.steps[1]["answer"], "yes")
        self.assertIn("added", s.steps[1])

    def test_revisit_keeps_not_sure_answer(self):
        s, _ = start(B)
        s.answer("not_sure")
        s.answer("yes")
        s.choose_repair("add")
        s.revisit("S4")
        s.answer("no")
        self.assertEqual(s.steps[0]["answer"], "not_sure")
        self.assertEqual(s.steps[1]["answer"], "no")

    def test_retained_answer_conflict_is_not_silently_discarded(self):
        import copy
        scenarios = copy.deepcopy([SCENARIOS[0], SCENARIOS[3]])
        scenarios[1].pop("repair")
        rule = lambda event, condition, action: {"when": [event], "if": condition,
                                               "device": "hallway_light", "do": action}
        generated = readings.Generated("x", {"kind": "test"}, {}, readings=[
            {"id": "R1", "label": "arrival only", "rules": [rule("arrive", ["dark"], "on")]},
            {"id": "R2", "label": "sunset and off", "rules": [rule("sunset", ["home"], "on"),
                                                                  rule("leave", [], "off")]},
        ])
        s = Session(generated, scenarios, strategy="boundary")
        s.answer("yes")
        s.answer("yes")
        self.assertEqual(s.stage, "confirm")
        s.revisit("S1")
        s.answer("no")
        self.assertEqual(s.stage, "none")
        self.assertEqual([(step["scenario"], step["answer"]) for step in s.steps], [("S1", "no"), ("S4", "yes")])

    def test_revisit_rejects_unknown_or_unanswered_question(self):
        s, _ = start(A)
        s.answer("no")
        self.assertEqual(s.stage, "confirm")
        with self.assertRaises(ValueError):
            s.revisit("S4")
        self.assertEqual(s.stage, "confirm")
        s.decide("save")
        with self.assertRaises(ValueError):
            s.revisit("S1")

    def test_wrong_transitions_are_refused(self):
        s, _ = start(B)
        with self.assertRaises(ValueError):
            s.choose_repair("add")
        with self.assertRaises(ValueError):
            s.answer("maybe")
        with self.assertRaises(ValueError):
            s.decide("save")


if __name__ == "__main__":
    unittest.main()
