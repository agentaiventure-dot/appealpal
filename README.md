# AppealPal

A denial letter in, a plan to appeal out. Paste the letter that denied your health-insurance claim, prior authorisation or benefit. AppealPal explains the reason in plain language, quotes the letter word for word, computes the appeal deadline in code from what the letter states, lists the evidence to gather and the questions to ask, and drafts an appeal letter you edit and send.

It explains and organises. It does not give legal or medical advice, and it never invents a date or a quote.

## Run (local open model, no cloud account)

```bash
ollama pull qwen2.5:7b && ollama serve &
APPEALPAL_ALLOW_LOCAL=1 LLM_API_KEY=local LLM_BASE_URL=http://127.0.0.1:11434 LLM_MODEL=qwen2.5:7b python3 -m appealpal   # http://127.0.0.1:8810
python3 -m pytest -q     # 7 offline tests against a fake model server
```

Any OpenAI-compatible endpoint on the allowlist works too (Groq, Nebius Token Factory, OpenAI): copy `.env.example`, set the three variables, and export them.

## How it stays honest
- The model must return a fixed JSON shape; wrong types, unknown fields, bad enums and invalid dates are rejected (`appealpal/analyze.py`, `validate`).
- Every quoted field (reason, deadline sentence, appeal channel, reference numbers) must appear verbatim in the letter (`quotes_in_letter`), or the answer is rejected.
- The appeal-by date is computed in code from the letter's stated date or day count (`compute_deadline`), with the basis shown to the person.
- The draft letter is built only from extracted facts and the person's own words.

## Public hosting hardening
AppealPal is designed to sit behind a public URL without a database or an account system:
- **Per-IP rate limit.** Every POST request is throttled per client IP (`X-Forwarded-For` first hop, or the socket address) by an in-memory fixed-window limiter (`appealpal/web.py`, `RateLimiter`). Default 30 requests/minute, set with `APPEALPAL_RATE_LIMIT_PER_MIN`. Over budget returns `429` with `Retry-After: 60`.
- **Request size limit.** `/api/*` POST bodies are capped (`MAX_CHARS` on the letter text, a hard byte cap on the whole request body); oversized requests are rejected with `413`/`400` before the body is parsed.
- **No persistence.** Nothing AppealPal receives is written to disk: no file writes, no database, no log line containing letter text, no cache directory. A letter lives only in the request/response objects for the life of that one HTTP call. (Confirmed by inspection: the only `open()` in the source tree is a read-only load of `fixtures/scenarios.json` by the demo mode's fake model server; the only `.write()` calls write the HTTP response to the socket, not to a file.)
- **`/healthz` reports mode**, not secrets: `{"ok": true, "mode": "demo"|"real"|"unconfigured", "model": "...", "rate_limit_per_minute": N}`. It never echoes the API key or base URL.

## Layout
```text
appealpal/llm.py       OpenAI-compatible client with origin allowlist
appealpal/analyze.py   prompt, validation, quote guard, deadline calculator, draft letter
appealpal/web.py       one-page UI and JSON API (standard library)
fixtures/              fictional letters, fake model server, scenarios
tests/                 pytest, offline
docs/evaluation.md     real-model results and weaknesses
```

Built during the AI Builders Hackathon 2026. MIT license.
