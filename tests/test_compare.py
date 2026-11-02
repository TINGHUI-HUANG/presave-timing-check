"""The offline comparison reproduces the Lab 3 finding on the hand-written Test B readings."""
import importlib.util
import json
import unittest
from pathlib import Path

from checker import readings, simulator

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("compare", ROOT / "tools" / "compare.py")
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)
SCENARIOS = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
B = next(r for r in json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))["requests"] if r["id"] == "B")


class Compare(unittest.TestCase):
    def test_divergence_misses_the_shared_error_that_combined_exposes(self):
        cands = simulator.distinct(readings.generate(B["text"], "fixed").readings, SCENARIOS)[0]
        devs, results = compare.evaluate(cands, SCENARIOS, B["intended"])
        self.assertEqual({sid: d["shared"] for sid, d in devs.items()}, {"S1": False, "S4": True})
        self.assertEqual((results[("divergence", 3)]["exposed"], results[("divergence", 3)]["correct"]), (1, 0))
        self.assertEqual((results[("combined", 2)]["exposed"], results[("combined", 2)]["correct"]), (2, 1))
        self.assertEqual(results[("combined", 3)]["asked"], 2)


if __name__ == "__main__":
    unittest.main()
