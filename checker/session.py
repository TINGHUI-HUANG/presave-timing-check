"""One request, from the typed sentence to Save or Edit.

The initiative rule is explicit and testable (Lecture 03, act / ask / wait):
- the system ASKS while the readings disagree in a scenario or a bug class applies, at most three times;
- with one reading left it PROPOSES the restated rule and WAITS;
- it never saves without the person's Save.
"""
import copy
import uuid

from . import repair, restate, selector, simulator

ANSWERS = {"yes": "Yes", "no": "No", "not_sure": "Not sure"}
WHY = {
    "differ": "Your words fit {n} rules, and they act differently here.",
    "flipped_trigger:dark": "Rules worded like yours often miss the moment it gets dark while you are already home.",
    "flipped_trigger:home": "Rules worded like yours often miss the moment you arrive after it is already dark.",
    "missing_reversal": "Rules worded like yours often turn the light on but never off.",
}
ERRORS = {
    "no_source": "I have no saved model output for this request and no model is connected, so I have not created a rule. "
                 "Try one of the example requests.",
    "model_failed": "The rule generator did not answer, so I have not created a rule. You can try again or rephrase.",
    "unusable": "The rule generator's reply did not fit the rule format, so I have not created a rule. "
                "You can try again or rephrase.",
}
INITIATIVE = ("Ask while the readings act differently in a scenario or a bug class applies (at most three questions); "
              "with one reading left, propose it and wait; never save without Save.")


def ids(readings):
    return [r["id"] for r in readings]


def flip(outcome):
    return "off" if outcome == "on" else "on"


class Session:
    def __init__(self, generated, scenarios, strategy="combined", budget=selector.BUDGET, logger=None, driver="browser"):
        self.id = uuid.uuid4().hex[:8]
        self.generated = generated
        self.request = generated.request
        self.scenarios = scenarios
        self.library = {s["id"]: s for s in scenarios}
        self.strategy, self.budget = strategy, budget
        self.logger, self.driver = logger, driver
        self.readings, self.merged, self.remaining = [], [], []
        self.steps = []          # one per question asked
        self.pending = None      # the question on screen
        self.offer = None        # the proposed repair on screen
        self.saved = None
        self._undo = []
        self._replay = []  # later answers retained while a previous question is edited
        self._held_current = None
        self.stage = None
        self._start()

    # -- log -----------------------------------------------------------------------------------
    def log(self, event, **data):
        if self.logger:
            self.logger({"session": self.id, "driver": self.driver, "event": event, **data})

    # -- transitions -----------------------------------------------------------------------------
    def _start(self):
        g = self.generated
        self.log("start", request=self.request, source=g.source,
                 sent={k: v for k, v in g.context.items() if k != "instruction"},
                 raw_reply=g.raw_text, unsupported=g.unsupported, problems=g.problems, notes=g.notes,
                 error=g.error, error_detail=g.error_detail)
        if g.error:
            self.stage = "error"
        elif g.unsupported:
            self.stage = "declined"
        else:
            self.readings, self.merged = simulator.distinct(g.readings, self.scenarios)
            self.remaining = list(self.readings)
            self.log("readings", readings=self.readings, merged=self.merged)
            self._advance()
        if self.stage in ("error", "declined"):
            self.log("result", stage=self.stage)

    def _advance(self):
        asked = [step["scenario"] for step in self.steps]
        if self._replay and self.remaining and len(asked) < self.budget:
            preserved = self._replay.pop(0)
            scenario = self.library[preserved["scenario"]]
            outcomes = {r["id"]: simulator.simulate(r, scenario) for r in self.remaining}
            self.pending = {"scenario": scenario, "reason": preserved["reason"], "outcomes": outcomes}
            self.stage = "question"
            self.log("answer_restored", scenario=scenario["id"], answer=preserved["answer"])
            self.answer(preserved["answer"], _restored=preserved)
            return
        scenario, reason = selector.next_scenario(self.remaining, self.scenarios, asked, self.strategy, self.budget)
        if scenario:
            outcomes = {r["id"]: simulator.simulate(r, scenario) for r in self.remaining}
            self.pending = {"scenario": scenario, "reason": reason, "outcomes": outcomes}
            self.stage = "question"
            self.log("question", number=len(asked) + 1, scenario=scenario["id"], reason=reason, outcomes=outcomes)
            return
        self.pending = None
        self.stage = {0: "none", 1: "confirm"}.get(len(self.remaining), "choose")
        self.log("result", stage=self.stage, remaining=ids(self.remaining))

    def _remember(self):
        self._undo.append(copy.deepcopy({name: getattr(self, name) for name in
                                        ("remaining", "steps", "pending", "offer", "stage", "_replay", "_held_current")}))

    def back(self):
        """Return to the previous step while retaining answers after that point."""
        if not self._undo or self.stage in ("saved", "edit"):
            raise ValueError("there is no previous step")
        known = copy.deepcopy(self.steps)
        if self._held_current:
            known = [step for step in known if step["scenario"] != self._held_current["scenario"]]
            known.append(copy.deepcopy(self._held_current))
        known.extend(copy.deepcopy(self._replay))
        previous = self._undo.pop()
        for name, value in previous.items():
            setattr(self, name, value)
        if self.stage == "question" and self.pending:
            target = self.pending["scenario"]["id"]
            matching = next((i for i, step in enumerate(known) if step["scenario"] == target), None)
            if matching is not None:
                self._held_current = known[matching]
                self._replay = known[matching + 1:]
        elif self.stage == "repair" and known:
            self._held_current = known[-1]
        self.log("back", stage=self.stage)

    def revisit(self, scenario_id):
        """Reopen a question, retaining later answers for re-evaluation."""
        if self.stage not in ("confirm", "choose"):
            raise ValueError("questions can only be revisited while reviewing")
        for index, previous in enumerate(self._undo):
            pending = previous.get("pending")
            if (previous["stage"] == "question" and pending
                    and pending["scenario"]["id"] == scenario_id):
                target = next(i for i, step in enumerate(self.steps) if step["scenario"] == scenario_id)
                retained = copy.deepcopy(self.steps[target + 1:])
                for name, value in previous.items():
                    setattr(self, name, copy.deepcopy(value))
                self._replay = retained
                self._held_current = None
                self._undo = self._undo[:index]
                self.log("revisit", scenario=scenario_id, stage=self.stage,
                         retained=[step["scenario"] for step in retained])
                return
        raise ValueError("that question is not available to revisit")

    def answer(self, reply, _restored=None):
        if self.stage != "question" or reply not in ANSWERS:
            raise ValueError("no question is waiting for that answer")
        self._remember()
        self._held_current = None
        scenario, outcomes = self.pending["scenario"], self.pending["outcomes"]
        step = {"scenario": scenario["id"], "reason": self.pending["reason"], "outcomes": outcomes, "answer": reply}
        if _restored is not None:
            step["restored"] = True
        self.steps.append(step)
        if reply == "not_sure":
            step.update(kept=ids(self.remaining), dropped=[])
            self.log("answer", scenario=scenario["id"], answer=reply, kept=step["kept"], dropped=[])
            self._advance()
            return
        wanted = scenario["yes"] if reply == "yes" else flip(scenario["yes"])
        step["wanted"] = wanted
        kept = [r for r in self.remaining if outcomes[r["id"]] == wanted]
        step.update(kept=ids(kept), dropped=[r["id"] for r in self.remaining if r not in kept])
        self.log("answer", scenario=scenario["id"], answer=reply, wanted=wanted, kept=step["kept"], dropped=step["dropped"])
        if kept:
            self.remaining = kept
            self._advance()
            return
        proposal = repair.propose(self.remaining, scenario, wanted)
        if proposal:
            rule, repaired = proposal
            self.offer = {"scenario": scenario, "rule": rule, "repaired": repaired}
            self.stage = "repair"
            self.log("repair_offered", scenario=scenario["id"], rule=rule)
            if _restored and _restored.get("added") == rule:
                self.choose_repair("add")
            elif _restored and _restored.get("declined") == rule:
                self.choose_repair("dont_add")
            return
        self.remaining = []
        self._advance()

    def choose_repair(self, choice):
        if self.stage != "repair" or choice not in ("add", "dont_add", "edit"):
            raise ValueError("no proposed rule is waiting for that choice")
        self._remember()
        self._held_current = None
        step = self.steps[-1]
        self.log("repair_choice", scenario=step["scenario"], choice=choice, rule=self.offer["rule"])
        if choice == "edit":
            self.stage = "edit"
            return
        if choice == "add":
            self.remaining = self.offer["repaired"]
            step.update(added=self.offer["rule"], kept=ids(self.remaining))
        else:
            step.update(declined=self.offer["rule"], kept=ids(self.remaining), dropped=[])
        self.offer = None
        self._advance()

    def decide(self, choice, store=None):
        """choice: "save" (one reading left), "use:<reading id>" (several left) or "edit"."""
        if self.stage == "saved":
            return  # a second click cannot save twice
        if choice == "edit" and self.stage in ("confirm", "choose", "none", "declined", "error", "question"):
            self.stage = "edit"
            self.log("decision", choice="edit")
            return
        if choice == "save" and self.stage == "confirm":
            reading = self.remaining[0]
        elif choice.startswith("use:") and self.stage == "choose":
            reading = next((r for r in self.remaining if r["id"] == choice[4:]), None)
            if reading is None:
                raise ValueError("no such rule")
        else:
            raise ValueError("nothing is waiting for that decision")
        self.saved = {"session": self.id, "request": self.request, "rule_text": restate.reading_text(reading),
                      "rules": reading["rules"], "source": self.generated.source}
        if store:
            store(self.saved)
        self.stage = "saved"
        self.log("decision", choice=choice, saved=reading["id"], rule_text=self.saved["rule_text"])

    # -- view ------------------------------------------------------------------------------------
    def _why(self, reason, scenario):
        if reason == "differ":
            return WHY["differ"].format(n=len(self.remaining))
        if reason == "flipped_trigger":
            return WHY[f"flipped_trigger:{scenario.get('sets')}"]
        return WHY.get(reason, "")

    def _history(self):
        out = []
        for n, step in enumerate(self.steps, 1):
            s = self.library[step["scenario"]]
            item = {"number": n, "scenario": s["id"], "events": [event for _, event in s["events"]],
                    "situation": s["text"], "question": s["question"], "answer": ANSWERS[step["answer"]]}
            if step.get("restored"):
                item["restored"] = True
            if "added" in step:
                item["note"] = "Added: " + restate.rule_text(step["added"])
            elif "declined" in step:
                item["note"] = "Not added: " + restate.rule_text(step["declined"])
            out.append(item)
        return out

    def _situations(self, reading):
        """Each library scenario with the rule's outcome and how it compares with the person's answer."""
        answered = {step["scenario"]: step for step in self.steps}
        rows = []
        for s in self.scenarios:
            outcome, step = simulator.simulate(reading, s), answered.get(s["id"])
            if step is None:
                checked, match = "not asked", None
            elif step["answer"] == "not_sure":
                checked, match = "you were not sure", None
            elif step["wanted"] == outcome:
                checked, match = "matches your answer", True
            else:
                checked, match = f"differs: you said it should be {step['wanted']}", False
            rows.append({"id": s["id"], "label": s["label"], "outcome": outcome, "checked": checked, "match": match})
        return rows

    def _card(self):
        if self.stage == "question":
            s = self.pending["scenario"]
            return {"kind": "question", "number": len(self.steps) + 1, "budget": self.budget, "situation": s["text"],
                    "question": s["question"], "why": self._why(self.pending["reason"], s),
                    "start": s["start"], "event": s["events"][0][1], "time": s["events"][0][0],
                    "options": [[k, v] for k, v in ANSWERS.items()]}
        if self.stage == "repair":
            return {"kind": "repair", "rule": restate.rule_text(self.offer["rule"]),
                    "options": [["add", "Add this rule"], ["dont_add", "Don't add"], ["edit", "Edit my request"]]}
        if self.stage == "confirm":
            reading = self.remaining[0]
            confirmed = [f"{row['label']}: light {row['outcome']} ({row['checked']})"
                         for row in self._situations(reading) if row["checked"] != "not asked"]
            mismatches = [row for row in self._situations(reading) if row["match"] is False]
            return {"kind": "confirm", "rules": [restate.rule_text(r) for r in reading["rules"]],
                    "never": restate.never(reading), "confirmed": confirmed, "mismatches": len(mismatches),
                    "rule_parts": reading["rules"],
                    "situations": self._situations(reading), "options": [["save", "Save"], ["edit", "Edit my request"]]}
        if self.stage == "choose":
            differ = simulator_differences(self.remaining, self.scenarios)
            return {"kind": "choose", "differences": differ,
                    "readings": [{"id": r["id"], "rules": [restate.rule_text(x) for x in r["rules"]],
                                  "rule_parts": r["rules"], "situations": self._situations(r),
                                  "never": restate.never(r)} for r in self.remaining],
                    "options": [[f"use:{r['id']}", f"Use and save rule {n}"] for n, r in enumerate(self.remaining, 1)]
                    + [["edit", "Edit my request"]]}
        if self.stage == "none":
            return {"kind": "none", "options": [["edit", "Edit my request"]]}
        if self.stage == "declined":
            return {"kind": "declined", "needs": self.generated.unsupported, "options": [["edit", "Edit my request"]]}
        if self.stage == "error":
            return {"kind": "error", "text": ERRORS[self.generated.error], "detail": self.generated.error_detail,
                    "options": [["retry", "Try again"], ["edit", "Edit my request"]]}
        if self.stage == "saved":
            return {"kind": "saved", "rules": [restate.rule_text(r) for r in self.saved["rules"]],
                    "never": restate.never({"rules": self.saved["rules"]})}
        return {"kind": "edit"}

    def _inspect(self):
        g = self.generated
        table = [{"id": s["id"], "label": s["label"],
                  "outcomes": {r["id"]: simulator.simulate(r, s) for r in self.readings}} for s in self.scenarios]
        return {"source": g.source, "sent": g.context, "raw_reply": g.raw_text,
                "readings": [{"id": r["id"], "label": r["label"], "text": restate.reading_text(r), "rules": r["rules"]}
                             for r in self.readings],
                "merged": self.merged, "notes": g.notes, "unsupported": g.unsupported, "problems": g.problems,
                "table": table, "steps": self.steps, "remaining": ids(self.remaining),
                "strategy": self.strategy, "budget": self.budget, "initiative": INITIATIVE}

    def view(self):
        return {"session": self.id, "stage": self.stage, "request": self.request, "source": self.generated.source,
                "can_back": bool(self._undo) and self.stage not in ("saved", "edit"),
                "history": self._history(),
                "retained": [{"scenario": step["scenario"], "situation": self.library[step["scenario"]]["text"],
                              "answer": ANSWERS[step["answer"]]} for step in self._replay],
                "card": self._card(), "inspect": self._inspect()}


def simulator_differences(readings, scenarios):
    """Scenarios in which the readings still act differently, with each reading's outcome."""
    rows = []
    for s in scenarios:
        outcomes = {r["id"]: simulator.simulate(r, s) for r in readings}
        if len(set(outcomes.values())) > 1:
            rows.append({"id": s["id"], "situation": s["text"], "outcomes": [outcomes[r["id"]] for r in readings]})
    return rows
