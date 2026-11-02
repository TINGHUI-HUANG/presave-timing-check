# Prompt log

Lecture 09's fixed testing loop: write the criteria first, run every fixed case, inspect the failures,
change one thing, run the same cases again.

**The model call.** `checker/readings.py` sends `prompts/readings_v1.txt` as the system instruction and
`Request: "<the sentence>"` as the only user content, with a response schema that fixes the reply's shape
(`unsupported`, `readings[].label`, `readings[].rules[].when/if/device/do`). Endpoint: Gemini API
`generateContent`; model `gemini-3.5-flash` (the service reported `gemini-3.6-flash` as the model version);
temperature 0.4.

## Success criteria (written before the first run)

| Id | Criterion | Checked by |
|---|---|---|
| C1 | The reply has the expected shape | program (`schema.check`) |
| C2 | An in-scope request uses only the vocabulary | program |
| C3 | One to three readings | program |
| C4 | The readings behave differently in at least one library scenario | program (simulator) |
| C5 | An out-of-scope request gives no readings and says what is missing | program |
| C6 | No reading adds a rule that the request neither states nor clearly implies | read by hand |

## Fixed cases

The seven requests in `data/requests.json`: the two Lab 3 tests (A, B), one request for each of the time
words "as soon as", "while" and "when" (C, D, E), and two out-of-scope requests (F, G).

## Runs

| When (UTC) | Prompt | Result | Change |
|---|---|---|---|
| 2 Nov 2026, 21:00 | v1 | D, E, F, G pass C1–C5; A, B, C fail with HTTP 503 (the service was busy) | none: not a prompt failure |
| 2 Nov 2026, 21:03 | v1 | A, B pass on retry; C fails again with HTTP 503 | none |
| 2 Nov 2026, 21:04 | v1 | C passes | none |
| — | — | C6, reading every reply: no reading adds a rule beyond the request | v1 kept |
| 2 Nov 2026, 21:05 | v1, second run into `data/stability_run.json` | A, B, G behave as in the first run; D returns one reading (never off) instead of two; C, E, F stopped by HTTP 503, then 429 (free quota used up) | none |

## What the recorded v1 readings say (replayed by the app)

| Request | Readings |
|---|---|
| A | one: on when arriving after dark; off when leaving |
| B | three: arriving or sunset while home; arriving after dark only; sunset while home only. None turns the light off |
| C | one: on when arriving after dark. It never acts at sunset and never turns the light off |
| D | two: both act on arriving after dark and at sunset while home; one also turns the light off on leaving |
| E | two: on at sunset, whether or not anyone is home; on at sunset only if home. Neither acts on arrival or turns the light off |
| F | declined: "front door lock" |
| G | declined: "Delays and going to bed events are unsupported" |

## Decision

Prompt v1 met every criterion on these cases, so it was not changed. What varies is the model, not the
prompt: the second run gave D a different set of readings. That is why the interface replays recorded
replies and why every recording keeps the exact context sent, the raw reply and the model version
(Lecture 08: identical calls can give different answers). The same cases are rerun whenever the prompt
changes; the Phase 3 evaluation will use published study tasks instead of my own requests.
