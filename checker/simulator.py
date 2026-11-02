"""Deterministic simulator: the light's state at the end of a scenario.

Outcomes shown to the person come from here, not from the model's own description of its
rule: the simulated outcome is observed, the model's summary would only be a claim (Lecture 12).
"""
from .schema import EFFECT


def simulate(reading, scenario):
    """Apply each event to the state; every rule whose events include it and whose conditions
    all hold just after it sets the light. A rule that does not fire leaves the light as it was."""
    state = dict(scenario["start"])
    for _time, event in scenario["events"]:
        key, value = EFFECT[event]
        state[key] = value
        for rule in reading["rules"]:
            if event in rule["when"] and all(state[c] for c in rule["if"]):
                state["light"] = rule["do"]
    return state["light"]


def table(readings, scenarios):
    """{scenario id: {reading id: outcome}}"""
    return {s["id"]: {r["id"]: simulate(r, s) for r in readings} for s in scenarios}


def distinct(readings, scenarios):
    """Merge readings that behave identically in every library scenario.

    The questions can only tell readings apart by their outcomes, so two readings with the same
    outcomes everywhere are one reading for this check. Returns (kept, merged) where merged lists
    (dropped id, kept id) pairs for the log.
    """
    kept, merged, seen = [], [], {}
    for r in readings:
        signature = tuple(simulate(r, s) for s in scenarios)
        if signature in seen:
            merged.append((r["id"], seen[signature]))
        else:
            seen[signature] = r["id"]
            kept.append(r)
    return kept, merged
