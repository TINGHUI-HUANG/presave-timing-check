"""Choose the next scenario question (at most three per request).

Two sources of questions:
- divergence: a scenario in which the remaining readings give different outcomes;
- bug-class probes: scenarios built for two bug classes that cut correct outcome predictions in
  Brackenbury et al. (2019), flipped triggers and missing reversals. They start from the
  readings' structure, so they can raise an error that every reading shares.

The interactive system uses "combined": divergence first, with the last question kept for a
probe (the Lab 3 revision). "divergence", "boundary" and "random" exist for tools/compare.py.
"""
from .schema import MAKES_TRUE
from .simulator import simulate

BUDGET = 3
STRATEGIES = ("combined", "divergence", "boundary", "random")


def uncovered(reading):
    """Conditions that none of their own rule's events can make true. Such a rule does not act at
    the moment the condition becomes true: a flipped trigger."""
    gaps = set()
    for rule in reading["rules"]:
        for c in rule["if"]:
            if not MAKES_TRUE[c] & set(rule["when"]):
                gaps.add(c)
    return gaps


def lacks_reversal(reading):
    """The reading turns the light on but never off: a missing reversal."""
    actions = {rule["do"] for rule in reading["rules"]}
    return "on" in actions and "off" not in actions


def inert(reading, scenario):
    """No rule of the reading changes the light in this scenario."""
    return simulate(reading, scenario) == scenario["start"]["light"]


def probes(readings, scenarios):
    """Bug-class scenarios that the readings' structure calls for, in library order.

    A flipped-trigger probe applies only if a reading has a rule whose condition is uncovered AND
    the reading as a whole does nothing in the probe scenario. Checking rules one at a time (the
    first version) also probed conditions that another rule of the same reading already covers,
    which spent questions for nothing (found with tools/compare.py on requests D and E).
    """
    no_off = any(lacks_reversal(r) for r in readings)
    out = []
    for s in scenarios:
        if s.get("probe") == "flipped_trigger":
            if any(s.get("sets") in uncovered(r) and inert(r, s) for r in readings):
                out.append(s)
        elif s.get("probe") == "missing_reversal" and no_off:
            out.append(s)
    return out


def differing(readings, scenarios):
    return [s for s in scenarios if len({simulate(r, s) for r in readings}) > 1]


def next_scenario(readings, scenarios, asked, strategy="combined", budget=BUDGET, rng=None):
    """Return (scenario, reason) or (None, None). reason is one of
    "differ", "flipped_trigger", "missing_reversal", "boundary", "random"."""
    if len(asked) >= budget:
        return None, None
    unasked = [s for s in scenarios if s["id"] not in asked]
    if not unasked:
        return None, None
    if strategy == "random":
        return rng.choice(unasked), "random"
    if strategy == "boundary":
        # Fixed bug-class boundaries in library order, whatever the readings are.
        fixed = [s for s in unasked if s.get("probe")]
        return (fixed[0], "boundary") if fixed else (None, None)
    differ = differing(readings, unasked)
    if strategy == "divergence":
        return (differ[0], "differ") if differ else (None, None)
    if strategy != "combined":
        raise ValueError(f"unknown strategy {strategy!r}")
    bug = [s for s in probes(readings, unasked) if s not in differ]
    if bug and (not differ or len(asked) == budget - 1):
        return bug[0], bug[0]["probe"]
    if differ:
        return differ[0], "differ"
    return None, None
