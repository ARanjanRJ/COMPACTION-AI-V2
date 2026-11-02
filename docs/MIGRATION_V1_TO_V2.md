# Migrating from V1 (D:\compaction) to V2

I have **not seen** your V1 files and did not modify them. Do not overwrite V1.

## Safe steps

- Keep `D:\compaction` untouched
- Unzip V2 to `D:\compaction-v2`
- V1's port is unknown to me. V2 defaults to 5000; set `PORT=5001` in `.env` if V1 uses 5000 (check V1's code or the address you open)
- V1 and V2 can run at the same time on different ports
- Ollama and `llama3.2:1b` are shared; no re-download needed

## What to send me when you are home

- V1 Python backend file(s)
- V1 `index.html` (and any CSS/JS)
- Any config or prompt text you tuned
- Do not send any `.env` or keys

## Expected mapping (assumed from your description)

| V1 feature | V2 |
|---|---|
| Ollama + llama3.2:1b | Same, via `OLLAMA_MODEL` |
| Python backend | `backend/app.py` (Flask) |
| HTML frontend | `static/` (holographic UI) |
| Compaction | Chunked, 9 sections, 3 modes |
| Copy Context | Kept (+ ChatGPT / Claude versions) |
| Download TXT | Kept (+ Markdown, handoff) |
| Ollama status | Real status panel, model check |

## After I see V1

- I can port any custom prompt wording or rules you liked
- Compare outputs on the same chat in both versions
