"""The capability envelope, and the checks every model reply passes before it is simulated.

A model reply is a proposal. Its shape and vocabulary are checked here in code, so a malformed
or out-of-scope reply becomes a caught error or a decline, never a rule (Lecture 12).
"""

DEVICES = {"hallway_light": "the hallway light"}
EVENTS = {"arrive": "you arrive home", "leave": "you leave home", "sunset": "it gets dark"}
CONDITIONS = {"home": "you are home", "dark": "it is dark"}
ACTIONS = ("on", "off")

# What each event does to the home's state.
EFFECT = {"arrive": ("home", True), "leave": ("home", False), "sunset": ("dark", True)}
# The events that can make each condition true.
MAKES_TRUE = {"home": {"arrive"}, "dark": {"sunset"}}

SUNSET = "18:00"
SCOPE = ("I can check rules for the hallway light that use arriving home, leaving home and sunset "
         "(sunset is fixed at 18:00 in this prototype). Other devices, clock times and delays are "
         "out of scope.")
MAX_READINGS = 3


def _terms(value):
    """A list of lower-case strings, or None if the value is not a list of strings."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    out = []
    for v in value:
        v = v.strip().lower()
        if v and v not in out:
            out.append(v)
    return out


def check(payload):
    """Check a parsed model reply.

    Returns a dict with:
      readings     the readings that passed, each {"id", "label", "rules"}
      unsupported  what the request needs that the envelope lacks (the model's own note and any
                   out-of-vocabulary term)
      problems     shape errors that make the reply unusable
      notes        anything dropped on the way, for the log
    """
    result = {"readings": [], "unsupported": [], "problems": [], "notes": []}
    if not isinstance(payload, dict):
        result["problems"].append("the reply is not a JSON object")
        return result
    note = payload.get("unsupported")
    if isinstance(note, str) and note.strip():
        result["unsupported"].append(note.strip())
    raw = payload.get("readings")
    if not isinstance(raw, list):
        result["problems"].append("'readings' is missing or is not a list")
        return result
    if len(raw) > MAX_READINGS:
        result["notes"].append(f"{len(raw) - MAX_READINGS} extra reading(s) dropped; the limit is {MAX_READINGS}")
    for n, item in enumerate(raw[:MAX_READINGS], 1):
        if not isinstance(item, dict) or not isinstance(item.get("rules"), list) or not item["rules"]:
            result["problems"].append(f"reading {n} has no list of rules")
            continue
        label = item.get("label") if isinstance(item.get("label"), str) and item["label"].strip() else f"reading {n}"
        rules = []
        for m, rule in enumerate(item["rules"], 1):
            where = f"reading {n}, rule {m}"
            if not isinstance(rule, dict):
                result["problems"].append(f"{where} is not an object")
                continue
            when, cond = _terms(rule.get("when")), _terms(rule.get("if", []))
            device = rule.get("device").strip().lower() if isinstance(rule.get("device"), str) else None
            action = rule.get("do").strip().lower() if isinstance(rule.get("do"), str) else None
            if when is None or cond is None or device is None or action is None:
                result["problems"].append(f"{where} is missing 'when', 'if', 'device' or 'do'")
                continue
            if not when:
                result["problems"].append(f"{where} has no event")
                continue
            outside = ([f"device '{device}'"] if device not in DEVICES else []) \
                + [f"event '{e}'" for e in when if e not in EVENTS] \
                + [f"condition '{c}'" for c in cond if c not in CONDITIONS] \
                + ([f"action '{action}'"] if action not in ACTIONS else [])
            for term in outside:
                if term not in result["unsupported"]:
                    result["unsupported"].append(term)
            rules.append({"when": when, "if": cond, "device": device, "do": action})
        result["readings"].append({"id": f"R{n}", "label": label.strip(), "rules": rules})
    return result
