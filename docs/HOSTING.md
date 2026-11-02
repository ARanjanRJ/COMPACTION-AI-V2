# Hosting research (₹0, no card, laptop OFF)

Research date: 30 Oct 2026. Sources are web pages I read; I did not sign up to or test any host.

## Bottom line

- **Self-hosted Ollama 24/7 with no card and no laptop: no verified option.**
- **Closest genuinely free alternative: Cloud mode**
  - Web app on Render free tier + AI from Ollama Cloud free tier
  - Works from phone/office with your laptop OFF
  - Trade-offs: not your own local model, text goes to ollama.com, the app sleeps, limits unpublished
- **Fully private option: local mode on your own PC (already built)**

## Azure for Students — checked, NOT recommended to rely on

- Microsoft's pages say:
  - Must be 18+ and a **full-time student at an accredited, degree-granting two- or four-year institution**
  - Verification is by your **institution's email address**
  - No credit card; $100 credit for 12 months; one subscription per person
  - Education/testing use; **not for commercial production use**
  - If credit runs out and you don't upgrade, resources are decommissioned
- Your risks (cannot be verified by me):
  - You are a **civil engineering diploma** student: Microsoft does not say whether a diploma counts
  - Your expected graduation is **2026** and it is now late October 2026: you may no longer be "currently enrolled"
  - You need a working college email that Microsoft recognises
- Even if approved: the 12-month free VM sizes listed are small burstable VMs; I have not checked their RAM or whether llama3.2:1b would be usable
- Verdict: **free to try** (no card), but treat it as unconfirmed until sign-up succeeds with your college email

## Free cloud AI: Ollama Cloud

- Official docs (docs.ollama.com/cloud) confirm:
  - API at `https://ollama.com/api/chat`, key from ollama.com/settings/keys, sent as a Bearer token
  - Prompts are processed to answer requests and not used to train models; **retention period not stated**
- A third-party page (freellm.net, updated 10 Sep 2026) claims: free tier, email signup, no card, 1 concurrent request, unpublished session/weekly caps. **The official page did not state a free plan**, so confirm at signup. If it asks for a card, stop.
- Long chats use several requests each (chunks + merge), so caps may be hit sooner
- Cloud models differ from `llama3.2:1b`; pick one listed for your account

## Free app hosting: Render

- Official Render page says:
  - Free web service sleeps after 15 min idle, ~1 min to wake
  - 750 free hours/month; suspended when used up
  - No persistent disk; local files lost on sleep
  - Card requirement **not stated** on the page; confirm at signup
- Fine for this app: it stores nothing server-side. History is in your browser only.
- Cannot run Ollama itself (small RAM, no disk, sleeps)

## Ruled out

- PythonAnywhere free: `ollama.com` is **not** on its outbound allowlist, so it cannot call Ollama Cloud
- Oracle Always Free: needs credit/debit card (reported)
- Koyeb: needs card (reported)
- Hugging Face Docker Spaces: reported blocked for new free accounts
- Codespaces: 120 h/month, not 24/7
- Colab: sessions end; not a stable server
- Android/Termux: unverified; not assumed

## What "free" costs you

- Cloud mode: privacy (text leaves your device), sleep delay, unknown caps
- Local mode: your PC must be on
- Mixed plan:
  - Home: local Ollama (private)
  - Away, laptop off: Cloud mode for non-sensitive chats
  - No server at all: Quick clean (no AI) in the browser
