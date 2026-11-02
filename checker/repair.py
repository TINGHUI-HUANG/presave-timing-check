"""Propose a missing rule when the person's answer matches none of the remaining readings.

Each probe scenario in the library carries a repair template for the outcome the person wants
there (for S4: "When you leave home: turn off the hallway light."). The rule is only proposed;
the person chooses Add, Don't add or Edit.
"""
from .simulator import simulate


def with_rule(reading, rule):
    return {"id": f"{reading['id']}+{rule['do']}", "label": f"{reading['label']}, plus the added rule",
            "rules": reading["rules"] + [dict(rule)]}


def propose(remaining, scenario, wanted):
    """Return (rule, repaired readings) if the scenario's template gives the wanted outcome for
    every remaining reading, else None."""
    template = scenario.get("repair", {}).get(wanted)
    if not template or not remaining:
        return None
    repaired = [with_rule(r, template) for r in remaining]
    if all(simulate(r, scenario) == wanted for r in repaired):
        return dict(template), repaired
    return None
