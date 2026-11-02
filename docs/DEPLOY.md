# Secure deployment guide

## Architecture

```
Browser -> COMPACTION (token required) -> Ollama (private only)
```

## Rules

- Never publish port 11434. Ollama has no login.
- Set `COMPACTION_ACCESS_TOKEN` (16+ chars) before using any non-local HOST. The app refuses to start otherwise.
- Use HTTPS in front (tunnel or reverse proxy) so the token is not sent in clear text.
- Keep `.env` out of Git.

## Docker (untested)

```powershell
copy .env.example .env      # add COMPACTION_ACCESS_TOKEN=<your 16+ char value>
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:1b
```

- App: http://127.0.0.1:5000 only; Ollama has no published port
- `docker compose config` parses OK; build and run were not tested

## Reaching it from office/mobile

- Needs your host machine switched ON
- Tailscale (private network, install on both devices) is the safest; free personal plan exists, terms may change
- Cloudflare quick tunnel: temporary URL, testing only; keep the token on
- Check each service's current free terms and whether it asks for a card

## Production process

- `gunicorn --chdir backend --workers 1 --threads 8 --timeout 0 app:app`
- Keep 1 worker so the rate limit and the one-job lock are shared

## Cloud mode: Render + Ollama Cloud (UNTESTED, written from docs)

- I have not deployed this. Steps are from Render/Ollama docs and may need adjusting.
- Safety:
  - Ollama is never exposed; the browser talks only to COMPACTION, which calls ollama.com with your key
  - The key lives only in Render's environment settings, never in the browser or Git
  - The app refuses to start with a non-local HOST unless an access token is set, and refuses an API key over http
- Steps when you are home or on a browser:
  - 1. Create `ollama.com` account, create an API key. If any step asks for a card, stop.
  - 2. Put the project on GitHub (without `.env`).
  - 3. Create a Render **Web Service** from the repo, **Free** instance. If it asks for a card, stop.
  - 4. Build command: `pip install -r requirements.txt`
  - 5. Start command: `gunicorn --chdir backend --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:$PORT app:app`
  - 6. Environment variables:
    - `HOST=0.0.0.0`
    - `COMPACTION_ACCESS_TOKEN=<your own 16+ char random value>`
    - `OLLAMA_BASE_URL=https://ollama.com`
    - `OLLAMA_API_KEY=<your key>`
    - `OLLAMA_MODEL=<a model your account lists>`
    - `PYTHON_VERSION=3.12.0`
  - 7. Open the Render URL on phone, enter the token, check the status panel, test with a non-sensitive chat.
- Known unknowns:
  - Whether Ollama Cloud accepts the `num_ctx` and `keep_alive` options this app sends
  - Real caps on the free tier
  - Behind Render's proxy all visitors share one rate-limit bucket (fine for one user)
- Do not paste secrets or private data in Cloud mode
