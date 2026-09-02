# Evaluation on the fixture letters

Run 2026-09-03 with a local open model (`qwen2.5:7b` on Ollama, loopback) through the same client used in production.

| Letter | Result | Time | Deadline computed | Notes |
|---|---|---|---|---|
| Claim denial (MRI, 180 days from letter date) | accepted | 6.6 s | 2027-02-16, basis "180 days from the letter date 2026-08-20" | reason quoted verbatim; external review flagged; reference ids quoted; one evidence item suggested |
| Prior authorisation denial (60 days) | accepted | 4.2 s | 2026-10-27, basis "60 days from the letter date 2026-08-28" | reason quoted verbatim; no external review (correct) |

Guards exercised by `python3 -m pytest` (7 tests): wrong types, bad enum, invalid dates, extra fields and quotes not found in the letter are rejected before anything is shown; deadlines are computed in code, never taken from the model.

## Known weaknesses
- Evidence suggestions from a small model are short (one item); a larger model gives fuller lists.
- Letters that state a deadline only as "promptly" or "as soon as possible" yield no date; the app says so and tells the person to ask the insurer in writing.
- English only.
