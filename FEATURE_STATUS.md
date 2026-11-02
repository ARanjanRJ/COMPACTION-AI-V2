# Feature status and test results

## Verified (ran, against a FAKE Ollama)

- 52 backend/API tests pass (incl. Ollama Cloud key: sent as Bearer, never in responses, wrong key gives clear error, refused over http): dedupe, chunking, modes, validation, errors, token, rate limit, busy, CORS/CSP, startup check, no content in logs, cancel frees slot
- 67 browser checks pass (Playwright): desktop, mobile (no horizontal scroll), Ollama offline, token flow, copy/download, history off by default
- Ruff `E9,F` clean; `docker compose config` parses; gunicorn starts and `/api/health` responds

- Cloud-mode UI text checked in a real browser with a mocked status response (screenshot 05-cloud)

## NOT verified

- Real Ollama Cloud call, Render deployment, free-tier limits, card requirements

- Real Ollama and real `llama3.2:1b` output quality
- Windows commands, Docker build/run, any cloud host, Android/Termux
- Large real chats (speed on your hardware)
