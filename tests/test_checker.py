"""Tests for the checker core. Run from the repository root:  py -3.11 -m unittest -v

The Lab3Regression tests check that the rebuilt modules give the outcome tables and question order
saved in lab3/runs, so the move from the terminal prototype changed no behaviour.
"""
import json
import re
import unittest
from pathlib import Path

from checker import repair, restate, schema, scripted, selector, simulator

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


SCENARIOS = load("data/scenarios.json")["scenarios"]
LIB = {s["id"]: s for s in SCENARIOS}
REQUESTS = {r["id"]: r for r in load("data/requests.json")["requests"]}
FIXED = {item["request"]: item["reply"] for item in load("data/fixed_readings.json")["requests"]}

B_BEFORE = "When you arrive home or it gets dark, if you are home and it is dark: turn on the hallway light."
B_AFTER = B_BEFORE + " When you leave home: turn off the hallway light."


def fixed(request_id):
    return schema.check(FIXED[REQUESTS[request_id]["text"]])["readings"]


def lab3_table(name):
    """The first outcome table in a Lab 3 transcript: {scenario id: [outcome per reading]}."""
    rows = {}
    for line in (ROOT / "lab3" / "runs" / name).read_text(encoding="utf-8").splitlines():
        match = re.match(r"\| (S\d) [^|]*\|(.*)\|\s*$", line)
        if match:
            if match.group(1) in rows:
                break  # the offline-check table starts
            rows[match.group(1)] = [cell.strip() for cell in match.group(2).split("|")]
    return rows


def rule(when, cond, do):
    return {"when": when, "if": cond, "device": "hallway_light", "do": do}


class Lab3Regression(unittest.TestCase):
    def test_outcome_tables_match_lab3(self):
        for request_id, name in [("A", "testA.md"), ("B", "testB_before.md")]:
            readings = fixed(request_id)
            expected = lab3_table(name)
            self.assertEqual(set(expected), {"S1", "S2", "S3", "S4"})
            for sid, outcomes in expected.items():
                self.assertEqual([simulator.simulate(r, LIB[sid]) for r in readings], outcomes, (name, sid))

    def test_divergence_only_repeats_lab3_before(self):
        run = scripted.run(fixed("B"), SCENARIOS, REQUESTS["B"]["intended"], "divergence")
        self.assertEqual(run["asked"], ["S1"])
        self.assertEqual([restate.reading_text(r) for r in run["remaining"]], [B_BEFORE])
        self.assertEqual(restate.never(run["remaining"][0]), ["It never turns the light off."])

    def test_combined_repeats_lab3_after(self):
        run = scripted.run(fixed("B"), SCENARIOS, REQUESTS["B"]["intended"], "combined")
        self.assertEqual(run["asked"], ["S1", "S4"])
        self.assertEqual([s["reason"] for s in run["steps"]], ["differ", "missing_reversal"])
        self.assertEqual(run["steps"][1]["added"], rule(["leave"], [], "off"))
        self.assertEqual([restate.reading_text(r) for r in run["remaining"]], [B_AFTER])

    def test_combined_test_a_costs_one_question(self):
        run = scripted.run(fixed("A"), SCENARIOS, REQUESTS["A"]["intended"], "combined")
        self.assertEqual(run["asked"], ["S1"])
        self.assertEqual(run["steps"][0]["reason"], "flipped_trigger")
        self.assertEqual(run["steps"][0]["answer"], "no")
        self.assertEqual(len(run["remaining"]), 1)


class Schema(unittest.TestCase):
    def test_out_of_vocabulary_terms_are_unsupported(self):
        result = schema.check({"unsupported": "", "readings": [
            {"label": "lock on leaving", "rules": [{"when": ["leave"], "if": [], "device": "front_door_lock", "do": "lock"}]}]})
        self.assertIn("device 'front_door_lock'", result["unsupported"])
        self.assertIn("action 'lock'", result["unsupported"])
        self.assertEqual(result["problems"], [])

    def test_model_note_counts_as_unsupported(self):
        result = schema.check({"unsupported": "a two-hour delay", "readings": []})
        self.assertEqual(result["unsupported"], ["a two-hour delay"])
        self.assertEqual(result["readings"], [])

    def test_malformed_replies_are_problems(self):
        self.assertTrue(schema.check("not json")["problems"])
        self.assertTrue(schema.check({"readings": "none"})["problems"])
        self.assertTrue(schema.check({"readings": [{"label": "x", "rules": [{"when": "arrive"}]}]})["problems"])
        self.assertTrue(schema.check({"readings": [{"label": "x", "rules": [rule([], [], "on")]}]})["problems"])

    def test_extra_readings_dropped_and_case_normalised(self):
        reading = {"label": "x", "rules": [{"when": ["Arrive"], "if": ["DARK"], "device": "Hallway_Light", "do": "ON"}]}
        result = schema.check({"unsupported": "", "readings": [reading] * 4})
        self.assertEqual(len(result["readings"]), 3)
        self.assertEqual(len(result["notes"]), 1)
        self.assertEqual(result["readings"][0]["rules"][0], rule(["arrive"], ["dark"], "on"))


class Behaviour(unittest.TestCase):
    def test_readings_with_identical_outcomes_are_merged(self):
        x = {"id": "R1", "label": "x", "rules": [rule(["arrive"], ["dark"], "on")]}
        y = {"id": "R2", "label": "y", "rules": [rule(["arrive"], ["dark", "home"], "on")]}
        kept, merged = simulator.distinct([x, y], SCENARIOS)
        self.assertEqual([r["id"] for r in kept], ["R1"])
        self.assertEqual(merged, [("R2", "R1")])

    def test_sunset_rule_is_probed_on_arrival(self):
        reading = {"id": "R1", "label": "sunset if home", "rules": [rule(["sunset"], ["home"], "on")]}
        self.assertEqual(selector.uncovered(reading), {"home"})
        self.assertEqual([s["id"] for s in selector.probes([reading], SCENARIOS)], ["S2", "S4"])
        scenario, reason = selector.next_scenario([reading], SCENARIOS, [], "combined")
        self.assertEqual((scenario["id"], reason), ("S2", "flipped_trigger"))

    def test_probe_skips_a_condition_another_rule_covers(self):
        # Gemini's readings of D: both act at sunset and on arrival; they differ only on leaving.
        both = [rule(["sunset"], ["home"], "on"), rule(["arrive"], ["dark"], "on")]
        d = [{"id": "R1", "label": "off on leaving", "rules": both + [rule(["leave"], [], "off")]},
             {"id": "R2", "label": "never off", "rules": list(both)}]
        run = scripted.run(d, SCENARIOS, REQUESTS["D"]["intended"], "combined")
        self.assertEqual(run["asked"], ["S4"])

    def test_shared_errors_are_raised_within_three_questions(self):
        # Gemini's readings of E: neither acts on arrival after dark and neither turns the light off.
        e = [{"id": "R1", "label": "sunset", "rules": [rule(["sunset"], [], "on")]},
             {"id": "R2", "label": "sunset if home", "rules": [rule(["sunset"], ["home"], "on")]}]
        run = scripted.run(e, SCENARIOS, REQUESTS["E"]["intended"], "combined")
        self.assertEqual(run["asked"], ["S5", "S2", "S4"])
        self.assertEqual([s["reason"] for s in run["steps"]], ["differ", "flipped_trigger", "missing_reversal"])
        final = run["remaining"][0]
        self.assertTrue(all(simulator.simulate(final, s) == REQUESTS["E"]["intended"][s["id"]] for s in SCENARIOS))
        divergence = scripted.run(e, SCENARIOS, REQUESTS["E"]["intended"], "divergence")
        self.assertEqual(divergence["asked"], ["S5"])

    def test_budget_is_never_exceeded(self):
        readings = fixed("B")
        for strategy in selector.STRATEGIES:
            for seed in range(5):
                run = scripted.run(readings, SCENARIOS, REQUESTS["B"]["intended"], strategy, seed=seed)
                self.assertLessEqual(len(run["asked"]), selector.BUDGET, strategy)

    def test_boundary_strategy_ignores_the_readings(self):
        for request_id in ("A", "B"):
            run = scripted.run(fixed(request_id), SCENARIOS, REQUESTS[request_id]["intended"], "boundary")
            self.assertEqual(run["asked"], ["S1", "S2", "S4"])

    def test_repair_templates(self):
        arrival_only = fixed("B")[0]
        proposal = repair.propose([arrival_only], LIB["S1"], "on")
        self.assertEqual(proposal[0], rule(["sunset"], ["home"], "on"))
        self.assertEqual(simulator.simulate(proposal[1][0], LIB["S1"]), "on")
        self.assertIsNone(repair.propose([arrival_only], LIB["S3"], "on"))

    def test_restatement(self):
        self.assertEqual(restate.reading_text(fixed("A")[0]),
                         "When you arrive home, if it is dark: turn on the hallway light. "
                         "When you leave home: turn off the hallway light.")
        self.assertEqual(restate.never(fixed("A")[0]), [])


if __name__ == "__main__":
    unittest.main()
