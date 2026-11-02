# Test A: standard input (before revision)

Command: `python prototype/sim.py A`. Person: simulated; answers scripted from the intended behaviour written before the run.

## Input

> When I arrive home after sunset, turn on the hallway light, and turn it off when I leave.

## What the system received

- the typed request
- the schema: device hallway light; events arrive, leave, sunset; conditions home, dark
- the sunset time: 18:00 (fixed in this prototype)
- candidate readings [SIMULATED: fixed in tests.json in place of LLM output]:
  - Reading R1 (arrival after dark, off on leaving): When you arrive home, if it is dark: turn on the hallway light. When you leave home: turn off the hallway light.

## What it did

- Schema check [IMPLEMENTED]: every reading uses only supported devices, events and conditions.
- Simulation [IMPLEMENTED]: light state at the end of each library scenario:

| Scenario | Reading R1 |
|---|---|
| S1 home since 17:00, dark at 18:00 | off |
| S2 arrive at 19:00, after dark | on |
| S3 arrive at 15:00, daylight | off |
| S4 light on, leave at 23:30 | off |

- Selection [IMPLEMENTED]: up to 3 questions from scenarios where the readings differ; chosen again after each answer.

## What the person saw and did

System: "I can preview rules for the hallway light that use arriving, leaving and sunset (sunset 18:00). Other devices and times are out of scope."

No scenario separates the readings, so no question is asked.

**Result**

- System: "Here is the rule I will save: When you arrive home, if it is dark: turn on the hallway light. When you leave home: turn off the hallway light." [Save] [Edit]
- Person: Save
- Rule saved [SIMULATED; saving to Google Home or Home Assistant is PLANNED].

## Offline check (evaluation only; the person never sees this)

Intended behaviour, written before the run: On when I arrive after dark; nothing at sunset if I am already home; off when I leave.

| Scenario | Intended | Reading R1 | Saved rule | Asked? |
|---|---|---|---|---|
| S1 home since 17:00, dark at 18:00 | off | off | off | no |
| S2 arrive at 19:00, after dark | on | on | on | no |
| S3 arrive at 15:00, daylight | off | off | off | no |
| S4 light on, leave at 23:30 | off | off | off | no |

✗ = acts against the intended behaviour.

- Questions asked: 0.
- Deviations exposed before saving: none.
- Saved rule deviates from the intended behaviour in: none.
