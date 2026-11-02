"""Browser end-to-end test (Playwright + headless Chromium).

Real frontend + real backend, talking to a FAKE Ollama (tests/fake_ollama.py).
It proves the UI, wiring and error handling. It does NOT prove anything about
a real model's summary quality, a real Ollama install, or real hosting.

Run:  python tests/e2e_browser.py        (screenshots go to $SHOT_DIR or tests/_shots)
"""
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fake_ollama import FakeOllama  # noqa: E402

SHOTS = os.environ.get("SHOT_DIR", os.path.join(HERE, "_shots"))
os.makedirs(SHOTS, exist_ok=True)
results = []
SECRET = "ZEBRA-SECRET-7731"
CONVO = "\n".join(
    ["User: I am building a budget tracker called PennyWise for my family and I need your help planning it."]
    + ["Assistant: Sure. Feature %d: we should discuss item %d in detail because it affects the design of the app." % (i, i * 7) for i in range(1, 30)]
    + ["User: Remember the deadline is 14 March and the budget is 5000 rupees. My code word is %s." % SECRET]
)


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ((" -> " + str(detail)) if (detail and not cond) else ""), flush=True)


def start_backend(port, env_extra):
    env = dict(os.environ, PORT=str(port), RATE_LIMIT_PER_MINUTE="1000", NO_PROXY="127.0.0.1")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(k, None)
    for k in ("COMPACTION_ACCESS_TOKEN", "OLLAMA_MODEL", "HOST"):
        env.pop(k, None)
    env.update(env_extra)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "app.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=1)
            return p
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("backend did not start")


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    fake = FakeOllama().start()
    p1, p2, p3 = free_port(), free_port(), free_port()
    procs = [
        start_backend(p1, {"OLLAMA_BASE_URL": fake.url}),
        start_backend(p2, {"OLLAMA_BASE_URL": "http://127.0.0.1:%d" % free_port()}),           # Ollama offline
        start_backend(p3, {"OLLAMA_BASE_URL": fake.url, "COMPACTION_ACCESS_TOKEN": "t" * 24}),  # needs a token
    ]
    try:
        with sync_playwright() as pw:
            run(pw, fake, "http://127.0.0.1:%d" % p1, "http://127.0.0.1:%d" % p2, "http://127.0.0.1:%d" % p3)
    finally:
        for p in procs:
            p.terminate()
        fake.stop()
    failed = [r for r in results if not r[1]]
    print("\n%d checks, %d failed" % (len(results), len(failed)))
    sys.exit(1 if failed else 0)


def wait_status(page, text, timeout=15000):
    page.wait_for_function("t => document.getElementById('pill').textContent.includes(t)", arg=text, timeout=timeout)


def _patch_waits():
    """The app's CSP forbids 'unsafe-eval' (a feature we want to keep). Playwright evaluates
    string expressions in wait_for_function with eval, so pass them as functions instead."""
    from playwright.sync_api import Page
    original = Page.wait_for_function

    def wait_for_function(self, expression, *a, **kw):
        if isinstance(expression, str) and "=>" not in expression:
            expression = "() => (" + expression + ")"
        return original(self, expression, *a, **kw)

    Page.wait_for_function = wait_for_function


def run(pw, fake, base, base_off, base_tok):
    _patch_waits()
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    page = ctx.new_page()
    errors, hosts = [], set()
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type in ("error", "warning") else None)
    page.on("response", lambda r: errors.append("HTTP %d %s" % (r.status, r.url)) if r.status >= 400 else None)
    page.on("request", lambda r: hosts.add(r.url.split("/")[2]) if r.url.startswith("http") else None)
    page.goto(base)

    # ---- startup + real status
    check("title and tagline shown", "COMPACTION" in page.title() and "Keep the context. Lose the clutter." in page.inner_text(".tagline"))
    wait_status(page, "Ollama online")
    check("backend row online", "online" in page.inner_text("#rowBackend"))
    check("Ollama row connected (real /api/tags)", page.inner_text("#rowOllama") == "connected")
    check("selected model displayed", page.inner_text("#rowModel") == "llama3.2:1b")
    check("installed models counted", page.inner_text("#rowInstalled") == "1 model(s)")
    check("model dropdown lists real installed models", page.eval_on_selector_all("#modelSelect option", "o=>o.map(x=>x.value)") == ["llama3.2:1b"])
    check("orb idle when online", page.evaluate("document.body.dataset.orb") == "idle")
    page.screenshot(path=os.path.join(SHOTS, "01-desktop-empty.png"), full_page=True)

    # ---- empty input
    page.click("#compactBtn")
    check("empty input -> clear message", "Paste a conversation first" in page.inner_text("#message"))
    page.click("#quickBtn")
    check("empty input on quick clean -> message", "Paste a conversation first" in page.inner_text("#message"))

    # ---- counts + compaction
    page.fill("#input", CONVO)
    check("input char count correct", page.inner_text("#inChars").replace(",", "") == str(len(CONVO)))
    check("input word count correct", page.inner_text("#inWords").replace(",", "") == str(len(CONVO.split())))
    page.click("#compactBtn")
    page.wait_for_function("document.getElementById('output').value.length>0", timeout=20000)
    page.wait_for_function("document.getElementById('compactBtn').disabled===false")
    out = page.input_value("#output")
    check("compaction output shown (structured sections)", out.startswith("## PROJECT / TOPIC") and "## PENDING TASKS & NEXT STEPS" in out)
    orig = len(CONVO)
    comp = len(out)
    expected = "%.1f%%" % ((1 - comp / orig) * 100)
    check("compression percentage calculated correctly", page.inner_text("#stRatio") == expected, (page.inner_text("#stRatio"), expected))
    check("original + compacted counts shown", ("%s chars" % format(orig, ",")) in page.inner_text("#stOrig") and ("%s chars" % format(comp, ",")) in page.inner_text("#stComp"))
    check("success message shown", "Done." in page.inner_text("#message"))
    check("model chip shows model used", page.inner_text("#stModel") == "llama3.2:1b")
    check("progress hidden after finish", page.is_hidden("#progress"))
    check("conversation text actually reached Ollama", SECRET in fake.requests[-1]["messages"][1]["content"])
    page.screenshot(path=os.path.join(SHOTS, "02-desktop-result.png"), full_page=True)

    # ---- modes
    for label, value in (("Short", "short"), ("Detailed", "detailed")):
        page.check('input[name="mode"][value="%s"]' % value, force=True)
        page.click("#compactBtn")
        page.wait_for_function("document.getElementById('compactBtn').disabled===false")
        check("mode %s sent to model" % label, fake.requests[-1]["messages"][1]["content"].startswith("Mode: " + label))
    page.check('input[name="mode"][value="balanced"]', force=True)

    # ---- editing the output updates counts
    page.fill("#output", "## KEY FACTS\n- edited")
    check("editing output updates compacted count", ("%d chars" % len("## KEY FACTS\n- edited")) in page.inner_text("#stComp"), page.inner_text("#stComp"))
    page.fill("#output", out)

    # ---- copy actions (real clipboard)
    page.click("#copyBtn")
    check("Copy Context puts the context on the clipboard", page.evaluate("navigator.clipboard.readText()") == out.strip())
    page.click("#copyGpt")
    clip = page.evaluate("navigator.clipboard.readText()")
    check("Copy for ChatGPT wraps the context", "=== COMPACTED CONTEXT ===" in clip and out.strip() in clip and "(unconfirmed)" in clip)
    page.click("#copyClaude")
    clip = page.evaluate("navigator.clipboard.readText()")
    check("Copy for Claude uses <previous_context>", "<previous_context>" in clip and out.strip() in clip)

    # ---- downloads (real files)
    with page.expect_download() as d:
        page.click("#dlTxt")
    f = d.value
    body = open(f.path(), encoding="utf-8").read()
    check("Download TXT file name + content", f.suggested_filename.endswith(".txt") and body.strip() == out.strip(), f.suggested_filename)
    with page.expect_download() as d:
        page.click("#dlMd")
    f = d.value
    body = open(f.path(), encoding="utf-8").read()
    check("Download Markdown has header + context", f.suggested_filename.endswith(".md") and body.startswith("# Compacted context") and out.strip() in body and "AI compaction (Ollama" in body)
    with page.expect_download() as d:
        page.click("#dlHandoff")
    body = open(d.value.path(), encoding="utf-8").read()
    check("Download AI handoff contains instructions + context", "END OF CONTEXT" in body and out.strip() in body)

    # ---- warnings
    fake.extra = "- team size 424242"
    page.click("#compactBtn")
    page.wait_for_function("document.getElementById('warnings').hidden===false")
    check("invented number is flagged in the UI", "424242" in page.inner_text("#warnings"))
    fake.extra = ""

    # ---- clear buttons
    page.click("#clearOutput")
    check("Clear output empties it and resets stats", page.input_value("#output") == "" and page.inner_text("#stRatio") == "–")
    page.click("#copyBtn")
    check("export with nothing to export -> message", "nothing to export" in page.inner_text("#message").lower())
    page.click("#clearInput")
    check("Clear input empties it and counts", page.input_value("#input") == "" and page.inner_text("#inChars") == "0")

    # ---- quick clean (no AI)
    dup = "User: please remember that the invoice number is ABC-123 and it must never change."
    page.fill("#input", "\n".join([dup, "Assistant: noted.", dup, dup, "```", "x = compute_long_name(a, b, c, d)", "x = compute_long_name(a, b, c, d)", "```"]))
    before = len(fake.requests)
    page.click("#quickBtn")
    o = page.input_value("#output")
    check("Quick clean removes repeats, keeps code lines", o.count("ABC-123") == 1 and o.count("compute_long_name") == 2, o)
    check("Quick clean is labelled as NOT AI and sends nothing to Ollama", "NOT AI" in page.inner_text("#warnings") and len(fake.requests) == before and page.inner_text("#stModel").startswith("none"))

    # ---- model missing
    page.click("#clearInput")
    fake.models = ["other:7b"]
    page.click("#recheck")
    page.wait_for_function("document.getElementById('modelHelp').hidden===false")
    check("default model missing -> pull command shown", page.inner_text("#pullCmd") == "ollama pull llama3.2:1b")
    check("other installed model is selected instead", page.input_value("#modelSelect") == "other:7b")
    fake.models = []
    page.click("#recheck")
    page.wait_for_function("document.getElementById('pill').textContent.includes('no model')")
    check("no models -> clear status and help", "no models" in page.inner_text("#modelHelpText") and page.is_disabled("#modelSelect"))
    page.fill("#input", CONVO)
    page.click("#compactBtn")
    page.wait_for_function("document.getElementById('message').dataset.kind==='error'")
    check("compacting with missing model -> useful error", "not installed" in page.inner_text("#message") and "ollama pull" in page.inner_text("#message"))
    fake.models = ["llama3.2:1b"]
    page.click("#recheck")
    wait_status(page, "Ollama online")

    # ---- Ollama failing mid-stream / garbage
    for mode, needle in (("error_mid", "out of memory"), ("garbage", "could not be read"), ("empty", "empty answer")):
        fake.mode = mode
        page.click("#compactBtn")
        page.wait_for_function("document.getElementById('compactBtn').disabled===false && document.getElementById('message').dataset.kind==='error'")
        check("Ollama '%s' -> error message shown" % mode, needle in page.inner_text("#message"), page.inner_text("#message"))
    fake.mode = "ok"

    # ---- cancel
    fake.mode, fake.delay, fake.closed = "slow", 0.05, False
    page.click("#compactBtn")
    page.wait_for_selector("#cancelBtn:not([hidden])")
    check("orb switches to 'working' while compacting", page.evaluate("document.body.dataset.orb") == "working")
    check("progress bar visible while working", page.is_visible("#progress"))
    page.click("#cancelBtn")
    page.wait_for_function("document.getElementById('compactBtn').disabled===false")
    check("Cancel stops the job and says so", "Cancelled" in page.inner_text("#message"))
    t0 = time.time()
    while time.time() - t0 < 8 and not fake.closed:
        time.sleep(0.1)
    check("Cancel closed the connection to Ollama", fake.closed)
    fake.mode, fake.delay = "ok", 0

    # ---- history: off by default, stores result only, deletable
    page.evaluate("localStorage.clear()")
    page.reload(); wait_status(page, "Ollama online")
    page.fill("#input", CONVO); page.click("#compactBtn")
    page.wait_for_function("document.getElementById('output').value.length>0")
    check("history is OFF by default (nothing stored)", page.evaluate("localStorage.getItem('compaction_history_v2')") is None)
    page.click("#historyBox summary"); page.check("#saveToggle")
    page.click("#compactBtn")
    page.wait_for_function("JSON.parse(localStorage.getItem('compaction_history_v2')||'[]').length===1")
    stored = page.evaluate("localStorage.getItem('compaction_history_v2')")
    check("history saves the compacted result only, never the original", SECRET not in stored and "PROJECT / TOPIC" in stored)
    check("history item listed", page.locator("#historyList li").count() == 1 and "balanced" in page.inner_text("#historyList"))
    page.click("#clearOutput"); page.click("#historyList >> text=Load")
    check("history item can be loaded", page.input_value("#output").startswith("## PROJECT"))
    page.click("#historyList >> text=Delete")
    check("history item can be deleted", "No saved results" in page.inner_text("#historyList"))
    page.click("#clearHistory")

    # ---- responsive
    page.set_viewport_size({"width": 390, "height": 844})
    page.reload(); wait_status(page, "Ollama online")
    check("mobile: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    ys = page.evaluate("['.orb','#input','#output','.system'].map(s=>document.querySelector(s).getBoundingClientRect().top)")
    check("mobile: stacked order orb < input < output < status", ys == sorted(ys), ys)
    small = page.evaluate("[...document.querySelectorAll('button,.modes span')].filter(e=>e.offsetParent!==null).filter(e=>e.getBoundingClientRect().height<36).length")
    check("mobile: tap targets are not tiny", small == 0, small)
    page.screenshot(path=os.path.join(SHOTS, "03-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 900, "height": 900})
    check("tablet: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    page.set_viewport_size({"width": 1440, "height": 900})
    xs = page.evaluate("['.system','.center','.output-panel'].map(s=>document.querySelector(s).getBoundingClientRect().left)")
    check("desktop: three columns (status | orb+input | output)", xs == sorted(xs) and len(set(round(x) for x in xs)) == 3, xs)

    # ---- accessibility smoke
    unnamed = page.evaluate("""[...document.querySelectorAll('button')].filter(b=>!(b.textContent.trim()||b.getAttribute('aria-label'))).length""")
    check("every button has a name", unnamed == 0)
    unlabeled = page.evaluate("""[...document.querySelectorAll('textarea,select,input')].filter(e=>e.type!=='radio'&&e.type!=='checkbox').filter(e=>!(e.labels&&e.labels.length)).length""")
    check("every field has a label", unlabeled == 0)
    check("page language set", page.evaluate("document.documentElement.lang") == "en")

    # ---- privacy: only same-origin requests
    check("no third-party requests (only the backend origin)", hosts == {base.split("//")[1]}, hosts)
    # the deliberate "model not installed" test makes /api/compact answer HTTP 404; ignore only that call
    real = [e for e in errors if "/api/compact" not in e and "status of 404" not in e]
    check("no console errors / CSP violations / failed asset loads", not real, real[:3])

    # ---- Ollama offline (separate backend)
    off = ctx.new_page()
    off.goto(base_off)
    wait_status(off, "Ollama offline")
    check("offline: status panel shows not reachable", off.inner_text("#rowOllama") == "not reachable" and off.evaluate("document.body.dataset.orb") == "offline")
    check("offline: troubleshooting command shown", off.inner_text("#pullCmd") == "ollama serve")
    off.fill("#input", CONVO); off.click("#compactBtn")
    off.wait_for_function("document.getElementById('message').dataset.kind==='error'")
    check("offline: compact gives a useful error", "Cannot reach Ollama" in off.inner_text("#message"), off.inner_text("#message"))
    off.screenshot(path=os.path.join(SHOTS, "04-offline.png"), full_page=True)

    # ---- access token (separate backend)
    tok = ctx.new_page()
    tok.goto(base_tok)
    tok.wait_for_selector("#tokenCard:not([hidden])")
    check("token required: card shown and Ollama data hidden", "locked" in tok.inner_text("#rowOllama") and tok.inner_text("#rowModel") in ("–", ""))
    tok.fill("#tokenInput", "wrong-token-wrong-token-xx"); tok.click("#tokenSave")
    tok.wait_for_function("document.getElementById('rowAccess').textContent.includes('rejected')")
    check("wrong token is rejected", True)
    tok.fill("#tokenInput", "t" * 24); tok.click("#tokenSave")
    wait_status(tok, "Ollama online")
    check("right token unlocks", "accepted" in tok.inner_text("#rowAccess") and tok.is_hidden("#tokenCard"))
    tok.fill("#input", CONVO); tok.click("#compactBtn")
    tok.wait_for_function("document.getElementById('output').value.length>0")
    check("compaction works with token", tok.input_value("#output").startswith("## PROJECT"))
    check("token is not stored in localStorage", "t" * 24 not in tok.evaluate("JSON.stringify(Object.assign({}, localStorage))"))
    browser.close()


if __name__ == "__main__":
    main()
