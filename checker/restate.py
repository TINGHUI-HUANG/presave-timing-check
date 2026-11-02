"""Plain-words restatement, built from the checked rule itself rather than from model prose."""
from .schema import CONDITIONS, DEVICES, EVENTS
from .selector import lacks_reversal


def rule_text(rule):
    text = "When " + " or ".join(EVENTS[e] for e in rule["when"])
    if rule["if"]:
        text += ", if " + " and ".join(CONDITIONS[c] for c in rule["if"])
    return f"{text}: turn {rule['do']} {DEVICES[rule['device']]}."


def reading_text(reading):
    return " ".join(rule_text(rule) for rule in reading["rules"])


def never(reading):
    """What the rule will never do, stated outright (Lecture 12: state what did not happen)."""
    actions = {rule["do"] for rule in reading["rules"]}
    notes = []
    if lacks_reversal(reading):
        notes.append("It never turns the light off.")
    if "on" not in actions:
        notes.append("It never turns the light on.")
    return notes
