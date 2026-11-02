"""Deterministic simulator: the light's state at the end of a scenario.

Outcomes shown to the person come from here, not from the model's own description of its
rule: the simulated outcome is observed, the model's summary would only be a claim (Lecture 12).
"""
from itertools import product

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


def state_cases():
    """Every possible state and supported single event (events update their state first)."""
    for home, dark, light in product((False, True), (False, True), ("off", "on")):
        for event in EFFECT:
            yield {"start": {"home": home, "dark": dark, "light": light},
                   "events": [["", event]]}


def conflicts(reading):
    """Report simultaneous opposite actions, independent of rule ordering."""
    for scenario in state_cases():
        state = dict(scenario["start"])
        event = scenario["events"][0][1]
        key, value = EFFECT[event]
        state[key] = value
        actions = {r["do"] for r in reading["rules"]
                   if event in r["when"] and all(state[c] for c in r["if"])}
        if len(actions) > 1:
            return True
    return False


def distinct(readings, scenarios):
    """Merge only readings equivalent across every supported state and event."""
    cases = list(state_cases())
    kept, merged, seen = [], [], {}
    for r in readings:
        signature = tuple(simulate(r, s) for s in cases)
        if signature in seen:
            merged.append((r["id"], seen[signature]))
        else:
            seen[signature] = r["id"]
            kept.append(r)
    return kept, merged
