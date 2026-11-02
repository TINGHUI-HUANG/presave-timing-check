"""Pre-save timing check for one-sentence home automations.

schema     what the prototype can check, and the checks on every model reply
simulator  runs a reading through a scenario (deterministic)
selector   chooses the next scenario question
repair     proposes a missing rule when no reading matches an answer
restate    plain-words restatement of a rule
readings   candidate readings: recorded, live Gemini, or Lab 3's hand-written ones
session    one request from start to Save or Edit, with its log
"""
