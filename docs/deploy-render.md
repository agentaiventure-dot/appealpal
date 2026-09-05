# Deploying AppealPal to Render (free tier, no card required)

AppealPal has no database and no external dependencies beyond the standard library, so the whole
deploy is: push the repo, point Render at the `Dockerfile`, and let it boot in demo mode.

**Build status:** the `Dockerfile` was written and reviewed but its `docker build` was **not**
verified in this session, because Docker Desktop is not running here (`docker info` fails to
reach `unix:///Users/.../docker.sock`). The image is a thin two-`COPY`-layer wrapper around the
stock `python:3.12-slim` base with no pip install step, and `CMD ["python3", "-m", "appealpal"]`
is the exact entrypoint already exercised by the local run instructions and the test suite, but
verify it yourself with `docker build -t appealpal . && docker run -p 8810:8810 appealpal` (or let
Render's own build do that verification on first deploy) before treating it as proven.

## Option A: Blueprint (`render.yaml`), fastest

1. Push this repo to GitHub (`agentaiventure-dot/appealpal`, already the origin).
2. In the Render dashboard: **New**, then **Blueprint**.
3. Connect the GitHub repo. Render detects `render.yaml` at the repo root and shows one service,
   `appealpal`, of type **Web Service**, runtime **Docker**, plan **Free**.
4. Click **Apply**. Render builds the `Dockerfile` and deploys. No payment method is requested for
   the Free plan.
5. Wait for the deploy to go **Live**, then open the service URL Render assigns
   (`https://appealpal-xxxx.onrender.com`). You should see the AppealPal page with the
   "Demo mode: canned model responses for the sample letters; run locally with a real model"
   banner and four "Load sample" buttons.
6. Check `https://<your-service>.onrender.com/healthz`, it should return
   `{"ok": true, "mode": "demo", "model": "demo-canned-model", "rate_limit_per_minute": 30}`.

## Option B: Manual Web Service (no `render.yaml`)

1. Render dashboard, **New**, then **Web Service**.
2. Connect the GitHub repo `agentaiventure-dot/appealpal`, branch `main`.
3. **Runtime**: Docker. Render finds the `Dockerfile` at the repo root automatically, leave
   "Dockerfile Path" as `./Dockerfile`.
4. **Instance Type**: Free.
5. **Environment Variables** (Render, the service, Environment tab), add:
   - `HOST` = `0.0.0.0`
   - `APPEALPAL_PUBLIC` = `1`
   - `APPEALPAL_DEMO` = `1`
   - `APPEALPAL_RATE_LIMIT_PER_MIN` = `30` (optional; this is already the default)
   - Do **not** set `PORT`. Render injects it automatically and the app reads it via
     `os.environ.get("PORT", ...)`.
6. **Health Check Path**: `/healthz`.
7. Click **Create Web Service**. Render builds and deploys; watch the **Logs** tab for
   `AppealPal at http://0.0.0.0:<port>  mode=demo  model=demo-canned-model`.

## Free-tier behavior to expect

- The service **spins down after 15 minutes of inactivity** and takes about 30 to 50 seconds to
  wake on the next request (Render free-tier cold start). The first click after idle time will
  feel slow; that is Render waking the container, not AppealPal.
- No outbound network calls happen in demo mode (the "model" is an in-process fake server), so
  there is nothing to allowlist on Render's side.

## Switching the hosted demo to a real model

Demo mode (`APPEALPAL_DEMO=1`) is the default so the service runs with zero secrets and zero
cost. To point the same deployment at a real OpenAI-compatible model instead:

1. In the Render dashboard, service, **Environment**, set:
   - `APPEALPAL_DEMO` = `0`
   - `LLM_API_KEY` = your key
   - `LLM_BASE_URL` = one of the allowlisted origins in `appealpal/llm.py`
     (`https://api.groq.com/openai`, `https://api.tokenfactory.nebius.com`,
     `https://api.openai.com`, or `https://router.huggingface.co`). The client refuses to send
     the key anywhere else.
   - `LLM_MODEL` = the model name for that provider (for example `llama-3.3-70b-versatile` on Groq).
2. Save. Render redeploys automatically on an env var change.
3. `/healthz` should now report `"mode": "real"` and the configured model name, never the key.
4. Mark `LLM_API_KEY` as a **Secret** (Render's env var UI supports this) so it never appears in
   build logs or is exposed to collaborators with only viewer access.

A real model is never required to demo AppealPal: the demo-mode banner and the four canned sample
letters are enough to show the full flow (plain-language reason, computed deadline, evidence
checklist, draft appeal letter) without any account, card, or API key.
