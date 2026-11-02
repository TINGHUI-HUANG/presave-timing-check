import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET = 3  # at most three questions per request

DEVICES = {"hallway_light": "the hallway light"}
EVENTS = {"arrive": "you arrive home", "leave": "you leave home", "sunset": "it gets dark"}
STATES = {"home": "you are home", "dark": "it is dark"}
ACTIONS = {"on", "off"}
EFFECT = {"arrive": ("home", True), "leave": ("home", False), "sunset": ("dark", True)}
SET_BY = {"home": {"arrive", "leave"}, "dark": {"sunset"}}
# Repair template added in Phase 4 for the missing-reversal bug class.
REVERSAL = {"when": ["leave"], "if": [], "device": "hallway_light", "do": "off"}

def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

def ids(readings):
    return ", ".join(r["id"] for r in readings)

def cap(text):
    return text[:1].upper() + text[1:]

# check every reading against the schema.
def schema_problems(reading):
    problems = []
    for rule in reading["rules"]:
        problems += [f"event '{e}'" for e in rule["when"] if e not in EVENTS]
        problems += [f"condition '{c}'" for c in rule["if"] if c not in STATES]
        if rule["device"] not in DEVICES:
            problems.append(f"device '{rule['device']}'")
        if rule["do"] not in ACTIONS:
            problems.append(f"action '{rule['do']}'")
    return problems

# deterministic simulator. Returns the light state at the end of a scenario.
def simulate(reading, scenario):
    state = dict(scenario["start"])
    for _time, event in scenario["events"]:
        key, value = EFFECT[event]
        state[key] = value
        for rule in reading["rules"]:
            if event in rule["when"] and all(state[c] for c in rule["if"]):
                state["light"] = rule["do"]
    return state["light"]

# bug classes from Brackenbury et al. (2019) that the readings' structure allows.
def bug_classes(readings):
    found = set()
    for reading in readings:
        for rule in reading["rules"]:
            # A condition that none of the rule's own events can make true: the rule
            # does not act at the moment that condition becomes true.
            if any(not SET_BY[c] & set(rule["when"]) for c in rule["if"]):
                found.add("flipped_trigger")
        actions = {rule["do"] for rule in reading["rules"]}
        if "on" in actions and "off" not in actions:
            found.add("missing_reversal")
    return found

# choose the next scenario to ask about, or None.
def next_scenario(readings, scenarios, asked, revised):
    unasked = [s for s in scenarios if s["id"] not in asked]
    differ = [s for s in unasked if len({simulate(r, s) for r in readings}) > 1]
    bug = []
    if revised:
        classes = bug_classes(readings)
        bug = [s for s in unasked if s.get("bug_class") in classes and s not in differ]
    if bug and (not differ or len(asked) == BUDGET - 1):
        return bug[0], "chosen by the bug-class check: " + bug[0]["bug_class"].replace("_", " ")
    if differ:
        return differ[0], "chosen because the readings differ"
    return None, None

# restate a reading in plain words.
def restate_rule(rule):
    text = "When " + " or ".join(EVENTS[e] for e in rule["when"])
    if rule["if"]:
        text += ", if " + " and ".join(STATES[c] for c in rule["if"])
    return f"{text}: turn {rule['do']} {DEVICES[rule['device']]}."

def restate(reading):
    return " ".join(restate_rule(rule) for rule in reading["rules"])

def with_reversal(reading):
    return {"id": reading["id"] + "+off", "label": reading["label"] + ", off on leaving",
            "rules": reading["rules"] + [REVERSAL]}

class ScriptedPerson:

    def __init__(self, intended):
        self.intended = intended

    def answer(self, scenario):
        return "yes" if self.intended[scenario["id"]] == scenario["yes"] else "no"

    def repair(self, scenario, repaired):
        fits = all(simulate(r, scenario) == self.intended[scenario["id"]] for r in repaired)
        return "add" if fits else "don't add"

    def decide(self, options):
        labels = [label for _key, label in options]
        return "save" if "save" in labels else "edit"


class TypedPerson:

    def ask(self, options):
        keys = dict(options)
        menu = " / ".join(f"[{key}] {label}" for key, label in options)
        while True:
            reply = input(f"  {menu}: ").strip().lower()
            if reply in keys:
                return keys[reply]

    def answer(self, scenario):
        return self.ask([("y", "yes"), ("n", "no"), ("?", "not sure")])

    def repair(self, scenario, repaired):
        return self.ask([("a", "add"), ("d", "don't add"), ("e", "edit")])

    def decide(self, options):
        return self.ask(options)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("test", choices=["A", "B"])
    parser.add_argument("--revised", action="store_true",
                        help="bug-class scenarios and the proposed 'off' rule")
    parser.add_argument("--interactive", action="store_true", help="answer the questions yourself")
    parser.add_argument("--out", help="write the transcript to this Markdown file")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    library = load("scenarios.json")
    scenarios = library["scenarios"]
    test = load("tests.json")[args.test]
    readings = test["readings"]
    intended = test["intended"]
    person = TypedPerson() if args.interactive else ScriptedPerson(intended)
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    def finish():
        if args.out:
            Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    command = f"python prototype/sim.py {args.test}" + (" --revised" if args.revised else "")
    say(f"# {test['title']} ({'after' if args.revised else 'before'} revision)")
    say()
    say(f"Command: `{command}`. Person: " + (
        "answers typed at the terminal." if args.interactive else
        "simulated; answers scripted from the intended behaviour written before the run."))
    say()
    say("## Input")
    say()
    say(f"> {test['request']}")
    say()
    say("## What the system received")
    say()
    say("- the typed request")
    say("- the schema: device hallway light; events arrive, leave, sunset; conditions home, dark")
    say(f"- the sunset time: {library['sunset']} (fixed in this prototype)")
    say("- candidate readings [SIMULATED: fixed in tests.json in place of LLM output]:")
    for r in readings:
        say(f"  - Reading {r['id']} ({r['label']}): {restate(r)}")
    say()
    say("## What it did")
    say()
    problems = [p for r in readings for p in schema_problems(r)]
    if problems:
        say(f"- Schema check [IMPLEMENTED]: unsupported {', '.join(problems)}.")
        say()
        say("## What the person saw and did")
        say()
        say("- System: \"I can only preview hallway-light rules about arriving, leaving and sunset. "
            "Your request needs something else, so I have not created a rule.\" [Edit request]")
        finish()
        return
    say("- Schema check [IMPLEMENTED]: every reading uses only supported devices, events and conditions.")
    say("- Simulation [IMPLEMENTED]: light state at the end of each library scenario:")
    say()
    say("| Scenario | " + " | ".join(f"Reading {r['id']}" for r in readings) + " |")
    say("|---" * (len(readings) + 1) + "|")
    for s in scenarios:
        say(f"| {s['id']} {s['label']} | " + " | ".join(simulate(r, s) for r in readings) + " |")
    say()
    sources = ("scenarios where the readings differ, plus bug-class scenarios (the last question is "
               "kept for one)" if args.revised else "scenarios where the readings differ")
    say(f"- Selection [IMPLEMENTED]: up to {BUDGET} questions from {sources}; "
        "chosen again after each answer.")
    say()

    # Steps 5 and 6: ask, then keep the readings that match the answer.
    say("## What the person saw and did")
    say()
    say(f"System: \"I can preview rules for the hallway light that use arriving, leaving and sunset "
        f"(sunset {library['sunset']}). Other devices and times are out of scope.\"")
    say()
    remaining, asked = readings, []
    while remaining and len(asked) < BUDGET:
        scenario, reason = next_scenario(remaining, scenarios, asked, args.revised)
        if scenario is None:
            break
        asked.append(scenario["id"])
        say(f"**Q{len(asked)}** ({scenario['id']}, {reason})")
        say()
        say(f"- System: \"{scenario['text']} {scenario['question']}\" [Yes] [No] [Not sure]")
        reply = person.answer(scenario)
        say(f"- Person: {cap(reply)}")
        if reply == "not sure":
            say("- Kept: all readings (no answer to filter by).")
            say()
            continue
        wanted = scenario["yes"] if reply == "yes" else {"on": "off", "off": "on"}[scenario["yes"]]
        kept = [r for r in remaining if simulate(r, scenario) == wanted]
        if not kept and args.revised and scenario.get("bug_class") == "missing_reversal" and wanted == "off":
            repaired = [with_reversal(r) for r in remaining]
            say(f"- System: \"None of the readings turns the light off when you leave. "
                f"Add this rule? {restate_rule(REVERSAL)}\" [Add] [Don't add] [Edit]")
            choice = person.repair(scenario, repaired)
            say(f"- Person: {cap(choice)}")
            if choice == "edit":
                say("- The rule editor opens [PLANNED]. Nothing is saved.")
                remaining = None
                break
            kept = repaired if choice == "add" else remaining
            say(f"- Kept: {ids(kept)} (rule {'added' if choice == 'add' else 'not added'}).")
        else:
            dropped = [r for r in remaining if r not in kept]
            say(f"- Kept: {ids(kept) or 'none (no reading matches this answer)'}."
                + (f" Dropped: {ids(dropped)}." if kept and dropped else ""))
        say()
        remaining = kept
    if not asked:
        say("No scenario separates the readings" + (" and no bug class applies" if args.revised else "")
            + ", so no question is asked.")
        say()

    # Step 7: restate, then the person decides.
    saved = None
    if remaining is not None:
        say("**Result**")
        say()
        if len(remaining) == 1:
            say(f"- System: \"Here is the rule I will save: {restate(remaining[0])}\" [Save] [Edit]")
            options = [("s", "save"), ("e", "edit")]
        elif not remaining:
            say("- System: \"None of the readings matches your answers. You can edit the rule or "
                "rephrase your request.\" [Edit] [Rephrase]")
            options = [("e", "edit"), ("r", "rephrase")]
        else:
            say("- System: \"These readings still differ. Choose one or edit the rule:\"")
            for r in remaining:
                say(f"  - Reading {r['id']}: {restate(r)}")
            options = [(str(i), f"use reading {r['id']}") for i, r in enumerate(remaining, 1)]
            options.append(("e", "edit"))
        choice = person.decide(options)
        say(f"- Person: {cap(choice)}")
        if choice == "save":
            saved = remaining[0]
        elif choice.startswith("use reading "):
            saved = next(r for r in remaining if r["id"] == choice[len("use reading "):])
        if saved:
            say("- Rule saved [SIMULATED; saving to Google Home or Home Assistant is PLANNED].")
        else:
            say("- Nothing is saved; the person " + (
                "rephrases the request." if choice == "rephrase" else "edits the rule [PLANNED editor]."))
        say()

    # Evaluation only: compare with the intended behaviour, which the system never sees.
    say("## Offline check (evaluation only; the person never sees this)")
    say()
    say(f"Intended behaviour, written before the run: {test['intended_note']}")
    say()
    columns = [(f"Reading {r['id']}", r) for r in readings] + ([("Saved rule", saved)] if saved else [])
    say("| Scenario | Intended | " + " | ".join(name for name, _r in columns) + " | Asked? |")
    say("|---" * (len(columns) + 3) + "|")
    for s in scenarios:
        cells = []
        for _name, r in columns:
            outcome = simulate(r, s)
            cells.append(outcome + (" ✗" if outcome != intended[s["id"]] else ""))
        say(f"| {s['id']} {s['label']} | {intended[s['id']]} | " + " | ".join(cells)
            + f" | {'yes' if s['id'] in asked else 'no'} |")
    say()
    say("✗ = acts against the intended behaviour.")
    say()
    exposed = []
    for s in scenarios:
        wrong = [r for r in readings if simulate(r, s) != intended[s["id"]]]
        if s["id"] in asked and wrong:
            exposed.append(f"{s['id']} (reading{'s' if len(wrong) > 1 else ''} {ids(wrong)})")
    say(f"- Questions asked: {len(asked)}" + (f" ({', '.join(asked)})" if asked else "") + ".")
    say(f"- Deviations exposed before saving: {'; '.join(exposed) or 'none'}.")
    if saved is None:
        say("- Nothing was saved.")
    else:
        missed = []
        for s in scenarios:
            if simulate(saved, s) == intended[s["id"]]:
                continue
            if s["id"] in asked:
                why = "asked, but the deviation was kept"
            elif len({simulate(r, s) for r in readings}) == 1:
                why = "not asked: every reading gives the same outcome there, so the readings never differ"
            else:
                why = "not asked: no question left"
            missed.append(f"{s['id']} ({why})")
        say(f"- Saved rule deviates from the intended behaviour in: {'; '.join(missed) or 'none'}.")
    finish()


if __name__ == "__main__":
    main()
