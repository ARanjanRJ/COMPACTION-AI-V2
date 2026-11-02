# COMPACTION v2

**Keep the context. Lose the clutter.**
Compacts long AI chats into a structured handoff you can paste into ChatGPT or Claude. Uses **your own Ollama**. No paid API, no keys, no tracking.

## Honest status

- Tested: 52 backend/API tests and 67 browser checks, all against a **fake Ollama server**.
- NOT tested: a real Ollama model, real `llama3.2:1b` output quality, Windows commands, Docker build, any cloud host, Android/Termux.
- A 1B model can miss details or get things wrong. **Always read the result before relying on it.**
- Cloud: no card-free host was verified to run Ollama 24/7. The closest free option is **Cloud mode** (Render + Ollama Cloud): written from docs, NOT deployed, text leaves your device. See `docs/HOSTING.md` and `docs/DEPLOY.md`.
- Azure for Students: eligibility is doubtful for a diploma student graduating 2026. Unconfirmed.

## What it does

- Pastes in a long chat, outputs 9 sections:
  - Project/Topic, Key Facts, Preferences & Constraints, Decisions, Progress, Pending Tasks & Next Steps, Open Questions, Warnings, Instructions for the next assistant
- Modes: Short, Balanced, Detailed
- Removes exact repeated lines (code blocks untouched). Near-duplicates are counted, never deleted
- Flags numbers in the output that are not in the source (hallucination check)
- Copy Context, Copy for ChatGPT, Copy for Claude, Download TXT / Markdown / AI handoff
- Character and word counts, compression %, progress, cancel
- Optional local history (off by default, saves only the compacted result)
- Quick clean (no AI): works in the browser with no server

## Folder structure

```
backend/    Flask app, Ollama client, compaction logic, config
static/     index.html, css/, js/ (no frameworks)
tests/      fake Ollama, unit/API tests, browser test
docs/       HOSTING, DEPLOY, MIGRATION_V1_TO_V2
```

## Windows setup (PowerShell)

1. Install Python 3.10+ from python.org (tick "Add to PATH").
2. Install Ollama from https://ollama.com/download
3. In PowerShell:

```powershell
cd D:\compaction-v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull llama3.2:1b
copy .env.example .env
python backend\app.py
```

4. Open http://127.0.0.1:5000

- If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope Process Bypass`
- Model download is roughly 1.3 GB (third-party figure, unverified).
- These commands were not run on Windows by me.

## Troubleshooting

- "Ollama not reachable": open the Ollama app or run `ollama serve`
- "Model missing": run the `ollama pull` command shown in the left panel
- Port in use: change `PORT` in `.env`
- Slow: a 1B model on CPU is slow for long chats; use Short mode or shorter input
- App refuses to start with `HOST=0.0.0.0`: set `COMPACTION_ACCESS_TOKEN` (16+ chars)

## Privacy and security

- Text goes only to the Ollama URL you configure
- Conversation content is never logged (a test checks this)
- Ollama must never be exposed to the internet; only this app should be reachable
- Optional access token, rate limit, one job at a time, strict CSP
- `.env` is git-ignored; `.env.example` has placeholders only

## Tests

```powershell
pip install -r requirements-dev.txt
python -m unittest discover tests
```

## Upload to GitHub from Android

- Use the GitHub website or app: create repo, "Add file", "Upload files"
- Upload folders as a ZIP is not supported on GitHub; extract first, or use a computer
- Do not upload `.env`
