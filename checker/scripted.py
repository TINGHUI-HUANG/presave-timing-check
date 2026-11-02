"""A scripted person, for the tests and tools/compare.py only.

As in Lab 3, it answers every question from the intended behaviour written before the run, and it
adds a proposed rule when that rule gives the intended outcome. The interactive system never uses it.
"""
import random

from .repair import propose
from .selector import BUDGET, next_scenario
from .simulator import simulate


def answer(intended, scenario):
    return "yes" if intended[scenario["id"]] == scenario["yes"] else "no"


def run(readings, scenarios, intended, strategy="combined", budget=BUDGET, seed=0):
    """Ask up to `budget` questions with one strategy. Returns the questions asked, each step and
    the readings left at the end (one reading = the rule that would be saved)."""
    rng = random.Random(seed)
    remaining, asked, steps = list(readings), [], []
    while remaining and len(asked) < budget:
        scenario, reason = next_scenario(remaining, scenarios, asked, strategy, budget, rng)
        if scenario is None:
            break
        asked.append(scenario["id"])
        wanted = intended[scenario["id"]]
        kept = [r for r in remaining if simulate(r, scenario) == wanted]
        step = {"scenario": scenario["id"], "reason": reason, "answer": answer(intended, scenario)}
        if not kept:
            proposal = propose(remaining, scenario, wanted)
            if proposal:
                step["added"], kept = proposal
        step["kept"] = [r["id"] for r in kept]
        steps.append(step)
        remaining = kept
    return {"asked": asked, "steps": steps, "remaining": remaining}
