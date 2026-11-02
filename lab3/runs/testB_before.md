# Test B: problem input (before revision)

Command: `python prototype/sim.py B`. Person: simulated; answers scripted from the intended behaviour written before the run.

## Input

> Turn on the hallway light when I'm home after dark.

## What the system received

- the typed request
- the schema: device hallway light; events arrive, leave, sunset; conditions home, dark
- the sunset time: 18:00 (fixed in this prototype)
- candidate readings [SIMULATED: fixed in tests.json in place of LLM output]:
  - Reading A (arrival only): When you arrive home, if it is dark: turn on the hallway light.
  - Reading B (arrival or sunset): When you arrive home or it gets dark, if you are home and it is dark: turn on the hallway light.

## What it did

- Schema check [IMPLEMENTED]: every reading uses only supported devices, events and conditions.
- Simulation [IMPLEMENTED]: light state at the end of each library scenario:

| Scenario | Reading A | Reading B |
|---|---|---|
| S1 home since 17:00, dark at 18:00 | off | on |
| S2 arrive at 19:00, after dark | on | on |
| S3 arrive at 15:00, daylight | off | off |
| S4 light on, leave at 23:30 | on | on |

- Selection [IMPLEMENTED]: up to 3 questions from scenarios where the readings differ; chosen again after each answer.

## What the person saw and did

System: "I can preview rules for the hallway light that use arriving, leaving and sunset (sunset 18:00). Other devices and times are out of scope."

**Q1** (S1, chosen because the readings differ)

- System: "You have been home since 17:00. At 18:00 it gets dark. Should the hallway light come on at 18:00?" [Yes] [No] [Not sure]
- Person: Yes
- Kept: B. Dropped: A.

**Result**

- System: "Here is the rule I will save: When you arrive home or it gets dark, if you are home and it is dark: turn on the hallway light." [Save] [Edit]
- Person: Save
- Rule saved [SIMULATED; saving to Google Home or Home Assistant is PLANNED].

## Offline check (evaluation only; the person never sees this)

Intended behaviour, written before the run: On whenever I am home and it is dark, including at sunset if I am already home; off when I leave.

| Scenario | Intended | Reading A | Reading B | Saved rule | Asked? |
|---|---|---|---|---|---|
| S1 home since 17:00, dark at 18:00 | on | off ✗ | on | on | yes |
| S2 arrive at 19:00, after dark | on | on | on | on | no |
| S3 arrive at 15:00, daylight | off | off | off | off | no |
| S4 light on, leave at 23:30 | off | on ✗ | on ✗ | on ✗ | no |

✗ = acts against the intended behaviour.

- Questions asked: 1 (S1).
- Deviations exposed before saving: S1 (reading A).
- Saved rule deviates from the intended behaviour in: S4 (not asked: every reading gives the same outcome there, so the readings never differ).
