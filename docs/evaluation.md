# Evaluation

Two runs, both on 2026-09-05, both against the exact `appealpal.analyze.analyze()` / `ChatClient`
code path the production app uses. Numbers below are copied from the actual run output (pytest's
own summary line, and JSON written by the evaluation script), never hand-typed.

## 1. Fake-model suite (offline, deterministic)

```
$ python3 -m pytest -q
............
12 passed in 2.05s
```

12 tests, all against `fixtures/fake_llm.py` (a loopback fake of an OpenAI-compatible endpoint
that returns canned JSON per fixture letter). This is the suite CI would run: no network, no
Ollama, no API key. It covers the origin allowlist, all four sample letters end to end
(`analyze()` plus the deadline computation), the demo-mode banner/samples/friendly-explanation
path, the per-IP rate limiter, invented-quote and malformed-output rejection, and the draft-letter
builder.

## 2. Real-model run (local, `qwen2.5:7b` on Ollama)

Run against `http://127.0.0.1:11434`, model `qwen2.5:7b`, with
`APPEALPAL_ALLOW_LOCAL=1 LLM_API_KEY=local LLM_BASE_URL=http://127.0.0.1:11434 LLM_MODEL=qwen2.5:7b`,
over all four shipped sample letters plus two adversarial "stress" letters written to probe known
weak spots (a non-numeric deadline phrase, and a long narrative reason section that invites
paraphrase over verbatim quoting). This is the second run, taken *after* the prompt fix described
in Failure cases below; see that section for the before/after evidence.

| Letter | Result | Time | Tokens | Deadline computed |
|---|---|---|---|---|
| Claim denial (MRI, 180 days from letter date) | accepted | 14.77s | 784 | 2027-02-16, "180 days from the letter date 2026-08-20" |
| Prior authorization denial (60 days) | accepted | 12.66s | 674 | 2026-10-27, "60 days from the letter date 2026-08-28" |
| Benefit denial, orthodontic exclusion (explicit date) | accepted | 12.11s | 729 | 2026-10-30, "explicit date in the letter" |
| Benefit denial, gym reimbursement (no stated deadline) | accepted | 7.57s | 623 | not stated; "ask the insurer in writing and note the date you asked" |
| Stress: "appeal promptly" (no number, no date) | accepted | 8.56s | 646 | not stated; correctly refused to invent a number for "promptly" |
| Stress: 72-hour behavioral-health window, long narrative reason | accepted | 10.37s | 760 | 2026-08-21, "3 days from the letter date 2026-08-18" (see Failure cases) |

All 6/6 accepted: every quoted field (`reason_quote`, `deadline_quote`, `appeal_channel`,
`reference_ids`) passed the verbatim-in-letter check, and every JSON shape passed `validate()`.
No hallucinated dates or quotes were produced in either run.

## Failure cases

**Bug found and fixed during this evaluation: hours misread as days.** The first real-model run
(before the fix below) sent the behavioral-health stress letter, which states
`"You may appeal this determination within 72 hours..."`. The model correctly quoted that sentence
verbatim into `deadline_quote`, but filled `deadline_days` with `72` (treating the "72" as a day
count, ignoring the unit "hours"). `compute_deadline()` trusted that field and produced:

```json
"deadline_days": 72,
"deadline": {"appeal_by": "2026-10-29", "basis": "72 days from the letter date 2026-08-18"}
```

That is a genuinely dangerous failure for this product: a person with a 72-*hour* appeal window
for an urgent behavioral-health denial would have been told they had until late October, missing
their real deadline by more than two months. The root cause was the system prompt in
`appealpal/analyze.py`: `deadline_days (integer, or 0 if not stated)` never told the model what
unit to use, so it echoed the letter's raw number regardless of unit.

**Fix applied:** the prompt now reads `deadline_days (integer NUMBER OF CALENDAR DAYS ONLY; if the
letter's window is stated in hours, weeks or months, convert it to the equivalent number of days
(round down); if you cannot tell the unit, set this to 0 and rely on deadline_quote for the exact
wording; never confuse hours with days)`.

**Re-run after the fix** (the numbers in the table above), same letter:

```json
"deadline_days": 3,
"deadline": {"appeal_by": "2026-08-21", "basis": "3 days from the letter date 2026-08-18"}
```

72 hours converted correctly to 3 days, and the computed appeal-by date is now the real one.

**Known limitation, not fixed:** this fix is a prompt instruction, not a code-enforced guarantee.
`compute_deadline()` has no independent way to check that `deadline_days` is a plausible
conversion of whatever the letter actually said; it trusts the model's arithmetic once the JSON
shape and quote-verification pass. A model that ignores the instruction (a different or smaller
model, a future prompt regression) could reintroduce the same class of error, and the fake-model
test suite cannot catch it because the fake server ignores the system prompt entirely and returns
fixed canned JSON regardless of what the prompt says. Catching this class of bug requires either a
periodic real-model regression run like this one, or a code-side sanity check (for example,
flagging `deadline_days` values that are exact multiples of common hour-counts divided oddly, or
cross-checking against any hour/week/month words appearing near numbers in `deadline_quote`) that
was judged out of scope for this evaluation pass.

**Other weaknesses observed, not failures:**
- On the letter with an explicit `deadline_date`, the model still filled `deadline_days` with a
  non-zero, unrequested value (`60`, unrelated to the actual 61-day gap between the letter date and
  the appeal-by date). This does not affect the computed deadline: `compute_deadline()` always
  prefers `deadline_date` over `deadline_days` when both are present. It is model noise, not a
  correctness bug, but it shows `deadline_days` should not be trusted as evidence of anything when
  `deadline_date` is also set.
- Evidence and question lists from a 7B model are shorter (typically one to two items) than a
  larger hosted model would produce; this was already known from the first evaluation pass.
- English only; not tested against non-English letters.
