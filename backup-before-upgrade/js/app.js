/* COMPACTION v2 frontend. No frameworks, no analytics, no third-party requests.
 * Conversations stay in memory. Only the optional history (off by default) uses
 * localStorage, and it stores the compacted result only, never the original. */
(function () {
  "use strict";

  var CFG = window.COMPACTION_CONFIG || { apiBase: "" };
  var $ = function (id) { return document.getElementById(id); };
  var TOKEN_KEY = "compaction_token";
  var HIST_KEY = "compaction_history_v2";
  var SAVE_KEY = "compaction_save_history";
  var MODE_KEY = "compaction_mode";
  var MODEL_KEY = "compaction_model";

  var MODE_HINTS = {
    short: "Short: essentials only, at most about 5 bullets per section. Most compression, most risk of lost detail.",
    balanced: "Balanced: concise but keeps every decision, requirement and open task.",
    detailed: "Detailed: keeps reasoning, exact names, numbers and examples. Least compression."
  };

  var state = {
    busy: false, controller: null, limit: 100000, model: "", models: [],
    status: null, last: null, authRequired: false
  };

  // ---------- safe storage ----------
  function store(kind) {
    try { var s = window[kind]; s.setItem("_t", "1"); s.removeItem("_t"); return s; } catch (e) { return null; }
  }
  var local = store("localStorage"), session = store("sessionStorage");
  function lget(k, d) { try { var v = local && local.getItem(k); return v === null || v === undefined ? d : v; } catch (e) { return d; } }
  function lset(k, v) { try { if (local) local.setItem(k, v); } catch (e) { /* ignore */ } }
  function lremove(k) { try { if (local) local.removeItem(k); } catch (e) { /* ignore */ } }
  function token() { try { return (session && session.getItem(TOKEN_KEY)) || ""; } catch (e) { return ""; } }
  function setToken(t) { try { if (session) { if (t) session.setItem(TOKEN_KEY, t); else session.removeItem(TOKEN_KEY); } } catch (e) { /* ignore */ } }

  // ---------- helpers ----------
  function url(path) { return (CFG.apiBase || "") + path; }
  function authHeaders(extra) {
    var h = extra || {};
    if (token()) h.Authorization = "Bearer " + token();
    return h;
  }
  function words(t) { var m = String(t).trim().match(/\S+/g); return m ? m.length : 0; }
  function fmt(n) { return Number(n).toLocaleString(); }
  function stamp() {
    var d = new Date(), p = function (x) { return String(x).padStart(2, "0"); };
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "-" + p(d.getHours()) + p(d.getMinutes());
  }
  function selectedMode() { var r = document.querySelector('input[name="mode"]:checked'); return r ? r.value : "balanced"; }

  function message(text, kind) {
    var m = $("message");
    if (!text) { m.hidden = true; m.textContent = ""; return; }
    m.hidden = false; m.dataset.kind = kind || "info"; m.textContent = text;
  }

  function setRow(id, text, s) { var el = $(id); el.textContent = text; el.dataset.s = s || ""; }
  function setPill(text, s) { var p = $("pill"); p.textContent = text; p.dataset.state = s; }
  function setOrb(v) { document.body.dataset.orb = v; }

  // ---------- connection status (real checks) ----------
  function showModelHelp(text, cmd) {
    var box = $("modelHelp");
    if (text && state.status && state.status.cloud) {
      text = "Ollama Cloud is selected. If this persists, the server's API key may be wrong, the free usage limit may be used up, or the chosen model is not offered. Check the server settings.";
      cmd = "";
    }
    if (!text) { box.hidden = true; return; }
    box.hidden = false; $("modelHelpText").textContent = text; $("pullCmd").textContent = cmd || "";
    $("copyPull").hidden = !cmd;
  }

  function applyStatus(s) {
    state.status = s;
    var dw = $("dataWhere");
    if (dw) dw.textContent = s.cloud
      ? "CLOUD MODE: your text is sent to Ollama's cloud service (ollama.com) to be processed. Do not paste secrets or private data."
      : "Your text goes to your own Ollama server only.";
    state.limit = (s.limits && s.limits.maxInputChars) || state.limit;
    updateInputCounts();
    var o = s.ollama, def = s.model.default;
    state.models = o.models || [];
    var sel = $("modelSelect");
    sel.innerHTML = "";
    if (!o.reachable) {
      setRow("rowOllama", "not reachable", "bad");
      setRow("rowModel", def + " (unknown)", "warn");
      setRow("rowInstalled", "–", "warn");
      setPill("Ollama offline", "bad"); setOrb("offline");
      sel.disabled = true; sel.appendChild(new Option("(Ollama offline)", ""));
      showModelHelp("COMPACTION cannot reach Ollama. Open the Ollama app, or start it in a terminal, then press Re-check.", "ollama serve");
      return;
    }
    setRow("rowOllama", "connected", "ok");
    setRow("rowInstalled", state.models.length + " model(s)", state.models.length ? "ok" : "bad");
    if (!state.models.length) {
      sel.disabled = true; sel.appendChild(new Option("(no models installed)", ""));
      state.model = "";
      setRow("rowModel", def + " — not installed", "bad");
      setPill("Ollama online · no model", "warn"); setOrb("idle");
      showModelHelp("Ollama is running but has no models. Download the lightweight default model (about 1.3 GB):", "ollama pull " + def);
      return;
    }
    state.models.forEach(function (m) { sel.appendChild(new Option(m, m)); });
    sel.disabled = false;
    var saved = lget(MODEL_KEY, "");
    var pick = state.models.indexOf(state.model) >= 0 ? state.model
      : state.models.indexOf(saved) >= 0 ? saved
      : s.model.defaultInstalled ? def : state.models[0];
    state.model = pick; sel.value = pick;
    setRow("rowModel", pick, "ok");
    setPill("Ollama online · " + pick, "ok"); if (!state.busy) setOrb("idle");
    if (!s.model.defaultInstalled) {
      showModelHelp("The default model '" + def + "' is not installed, so '" + pick + "' is selected instead. To install the default:", "ollama pull " + def);
    } else showModelHelp("");
  }

  function showToken(show, text) {
    $("tokenCard").hidden = !show;
    if (show) { setRow("rowAccess", text || "token required", "warn"); $("tokenInput").focus(); }
  }

  async function refresh() {
    var health;
    try {
      var r = await fetch(url("/api/health"), { cache: "no-store" });
      health = await r.json();
    } catch (e) {
      setRow("rowBackend", "offline", "bad"); setRow("rowOllama", "unknown", "warn");
      setRow("rowModel", "–", ""); setRow("rowInstalled", "–", ""); setRow("rowAccess", "–", "");
      setPill("Backend offline", "bad"); setOrb("offline");
      return;
    }
    setRow("rowBackend", "online (v" + health.version + ")", "ok");
    state.authRequired = !!health.authRequired;
    if (state.authRequired && !token()) {
      showToken(true, "token required");
      setPill("Locked · enter token", "warn"); setRow("rowOllama", "locked", "warn");
      return;
    }
    var res;
    try { res = await fetch(url("/api/status"), { headers: authHeaders(), cache: "no-store" }); }
    catch (e) { setRow("rowBackend", "offline", "bad"); setPill("Backend offline", "bad"); setOrb("offline"); return; }
    if (res.status === 401) {
      setToken(""); showToken(true, "token rejected");
      setPill("Locked · wrong token", "warn"); return;
    }
    if (res.status === 429) { setPill("Too many requests", "warn"); return; }
    var s = await res.json();
    showToken(false);
    setRow("rowAccess", state.authRequired ? "token accepted" : "open (no token set)", state.authRequired ? "ok" : "warn");
    applyStatus(s);
  }

  // ---------- counts ----------
  function updateInputCounts() {
    var v = $("input").value;
    $("inChars").textContent = fmt(v.length);
    $("inWords").textContent = fmt(words(v));
    var lim = $("inLimit");
    lim.textContent = "limit " + fmt(state.limit) + " characters";
    lim.dataset.s = v.length > state.limit ? "bad" : "";
  }

  function ratioText(orig, comp) {
    if (!orig) return "–";
    var pct = (1 - comp / orig) * 100;
    return pct.toFixed(1) + "%" + (pct <= 0 ? " (not shorter)" : "");
  }

  function renderOutputStats() {
    var out = $("output").value, L = state.last;
    var cc = out.length, cw = words(out);
    if (!L || !out.trim()) {
      ["stOrig", "stComp", "stRatio", "stDup", "stModel", "stTime"].forEach(function (id) { $(id).textContent = "–"; });
      return;
    }
    $("stOrig").textContent = fmt(L.origChars) + " chars · " + fmt(L.origWords) + " words";
    $("stComp").textContent = fmt(cc) + " chars · " + fmt(cw) + " words";
    $("stRatio").textContent = ratioText(L.origChars, cc);
    $("stDup").textContent = String(L.dup) + (L.similar ? " (" + L.similar + " similar kept)" : "");
    $("stModel").textContent = L.model;
    $("stTime").textContent = L.ms != null ? (L.ms / 1000).toFixed(1) + " s" : "–";
  }

  function setWarnings(list) {
    var ul = $("warnings");
    ul.innerHTML = "";
    list.forEach(function (t) { var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
    ul.hidden = !list.length;
  }

  // ---------- compaction ----------
  function setBusy(b) {
    state.busy = b;
    $("compactBtn").disabled = b; $("quickBtn").disabled = b;
    $("cancelBtn").hidden = !b;
    $("modelSelect").disabled = b || !state.models.length;
    document.querySelectorAll('input[name="mode"]').forEach(function (r) { r.disabled = b; });
    $("progress").hidden = !b;
    if (b) { setOrb("working"); progress(0, 1, "Starting…"); }
    else setOrb(state.status && state.status.ollama.reachable ? "idle" : "offline");
  }

  function progress(done, total, text) {
    var pct = Math.max(5, Math.min(95, Math.round((done / Math.max(1, total)) * 100)));
    $("bar").style.width = pct + "%";
    $("track").setAttribute("aria-valuenow", String(pct));
    $("progressText").textContent = text || "";
  }

  function apiError(j, status) {
    var e = new Error((j && j.error && j.error.message) || ("Request failed (HTTP " + status + ")."));
    e.code = (j && j.error && j.error.code) || "http_" + status;
    return e;
  }

  var HINTS = {
    ollama_unavailable: " Start Ollama, then press Re-check connection.",
    ollama_auth: " The server's Ollama Cloud key is missing or wrong. Fix it in the host settings.",
    model_missing: " Install it with the command shown in the System status panel.",
    ollama_timeout: " Try the Short mode, a smaller conversation, or a faster model.",
    busy: "", unauthorized: " Enter the access token in the System status panel."
  };

  async function runCompact() {
    if (state.busy) return;
    var text = $("input").value;
    if (!text.trim()) { message("Paste a conversation first.", "error"); $("input").focus(); return; }
    if (text.length > state.limit) {
      message("This conversation has " + fmt(text.length) + " characters; the limit is " + fmt(state.limit) + ". Split it into parts and compact each one.", "error"); return;
    }
    message(""); setWarnings([]);
    var mode = selectedMode(), origChars = text.length, origWords = words(text), got = null;
    state.controller = new AbortController();
    setBusy(true);
    try {
      var res = await fetch(url("/api/compact"), {
        method: "POST", headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ text: text, mode: mode, model: state.model || undefined }),
        signal: state.controller.signal
      });
      if (!res.ok) throw apiError(await res.json().catch(function () { return null; }), res.status);
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = "";
      for (;;) {
        var r = await reader.read();
        if (r.done) break;
        buf += dec.decode(r.value, { stream: true });
        var idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          var line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 1);
          if (!line) continue;
          var ev = JSON.parse(line);
          if (ev.type === "stage" || ev.type === "progress") {
            progress(ev.done, ev.total, ev.message + (ev.generated_chars ? " (" + fmt(ev.generated_chars) + " characters written)" : ""));
          } else if (ev.type === "result") { got = ev; }
          else if (ev.type === "error") { throw apiError(ev, 200); }
        }
      }
      if (!got) throw Object.assign(new Error("The connection closed before a result arrived. Please try again."), { code: "stream_closed" });
      finishAi(got, origChars, origWords, mode);
    } catch (e) {
      if (e.name === "AbortError") { message("Cancelled. Nothing was saved.", "info"); }
      else if (e instanceof TypeError || e.name === "SyntaxError") {
        message("Cannot reach the COMPACTION backend. Make sure it is running (python backend/app.py) and try again.", "error");
        refresh();
      } else {
        message(e.message + (HINTS[e.code] || ""), "error");
        if (e.code === "ollama_unavailable" || e.code === "model_missing" || e.code === "unauthorized") refresh();
      }
    } finally {
      state.controller = null; setBusy(false);
    }
  }

  function finishAi(ev, origChars, origWords, mode) {
    var st = ev.stats;
    $("output").value = ev.context;
    state.last = { kind: "ai", origChars: origChars, origWords: origWords, dup: st.duplicates_removed, similar: st.similar_lines_kept,
      model: st.model, ms: st.elapsed_ms, mode: mode };
    var warns = [], pct = origChars ? (1 - ev.context.length / origChars) * 100 : 0;
    if (!st.format_ok) warns.push("The model did not follow the expected section format. Read the result carefully. Balanced or Detailed mode, or a larger model, usually helps.");
    if (st.unverified_numbers && st.unverified_numbers.length) warns.push("These numbers were not found in your original text, so they may be wrong: " + st.unverified_numbers.join(", ") + ". Please check them.");
    if (st.merge_truncated) warns.push("Some intermediate notes were cut to fit the model's limit. Increase MERGE_CHARS or use shorter input.");
    if (pct <= 0) warns.push("The result is not shorter than the original. Try Short mode or paste a longer conversation.");
    else if (pct > 90 && origChars >= 1000) warns.push("More than 90% was removed. Check that nothing important is missing.");
    setWarnings(warns);
    renderOutputStats();
    message("Done. Compacted " + fmt(origChars) + " → " + fmt(ev.context.length) + " characters (" + ratioText(origChars, ev.context.length) + "). Review it, then copy it into a new chat.", "success");
    saveHistory("ai", mode, st.model, origChars, origWords, ev.context);
  }

  function runQuick() {
    if (state.busy) return;
    var text = $("input").value;
    if (!text.trim()) { message("Paste a conversation first.", "error"); $("input").focus(); return; }
    var r = window.CompactionClean.dedupe(text);
    $("output").value = r.text;
    state.last = { kind: "clean", origChars: text.length, origWords: words(text), dup: r.removed, similar: r.similar, model: "none (no AI)", ms: null, mode: "clean" };
    setWarnings(["Quick clean only removes repeated lines. It is NOT AI and did not summarise anything."]);
    renderOutputStats();
    message("Quick clean removed " + r.removed + " repeated line(s). No AI was used.", "success");
    saveHistory("clean", "clean", "none", text.length, words(text), r.text);
  }

  // ---------- export ----------
  function currentContext() { return $("output").value.trim(); }

  function handoff(kind, ctx) {
    var rules = [
      "I'm continuing a conversation from another AI chat. Below is a compacted summary of it.",
      "How to use it:",
      "- Treat it as background context, not as a new request to answer.",
      '- Items marked "(unconfirmed)" are not verified. Ask me before relying on them.',
      '- Items marked "CONFLICT:" contradict each other. Ask me which one is right.',
      "- Do not invent details that are not in the context."
    ].join("\n");
    var close = "Reply with one short sentence confirming you have the context, then wait for my next message.";
    if (kind === "claude") return rules + "\n\n<previous_context>\n" + ctx + "\n</previous_context>\n\n" + close;
    return rules + "\n\n=== COMPACTED CONTEXT ===\n" + ctx + "\n=== END OF CONTEXT ===\n\n" + close;
  }

  function markdownDoc(ctx) {
    var L = state.last || {};
    var method = L.kind === "clean" ? "Quick clean (no AI, repeated lines removed)" : "AI compaction (Ollama, model " + (L.model || "unknown") + ", mode " + (L.mode || "unknown") + ")";
    return "# Compacted context\n\n- Generated by COMPACTION v2.0\n- Date: " + new Date().toLocaleString() + "\n- Method: " + method +
      "\n- Reduction: " + ratioText(L.origChars || 0, ctx.length) + "\n- Note: review before relying on it; compression can lose nuance.\n\n---\n\n" + ctx + "\n";
  }

  function copyText(text) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly", ""); ta.className = "sr";
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallback(); });
    }
    return Promise.resolve(fallback());
  }

  function needContext() {
    var c = currentContext();
    if (!c) { message("There is nothing to export yet. Compact a conversation first.", "error"); return null; }
    return c;
  }

  function doCopy(kind) {
    var c = needContext(); if (!c) return;
    var text = kind === "plain" ? c : handoff(kind, c);
    var label = kind === "plain" ? "Context" : kind === "claude" ? "Handoff for Claude" : "Handoff for ChatGPT";
    copyText(text).then(function (ok) {
      message(ok ? label + " copied. Paste it into a new chat." : "Copy was blocked by the browser. Select the text and copy it manually.", ok ? "success" : "error");
    });
  }

  function download(name, text, mime) {
    var blob = new Blob([text], { type: mime + ";charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  // ---------- history (optional, off by default) ----------
  function loadHistory() {
    try { var h = JSON.parse(lget(HIST_KEY, "[]")); return Array.isArray(h) ? h : []; } catch (e) { return []; }
  }
  function saveHistory(kind, mode, model, origChars, origWords, text) {
    if (lget(SAVE_KEY, "0") !== "1") return;
    var h = loadHistory();
    h.unshift({ id: Date.now().toString(36), ts: Date.now(), kind: kind, mode: mode, model: model, origChars: origChars, origWords: origWords, text: text });
    lset(HIST_KEY, JSON.stringify(h.slice(0, 30)));
    renderHistory();
  }
  function renderHistory() {
    var ul = $("historyList"), h = loadHistory();
    ul.innerHTML = "";
    if (!h.length) { var li = document.createElement("li"); li.textContent = "No saved results."; ul.appendChild(li); return; }
    h.forEach(function (it) {
      var li = document.createElement("li"), s = document.createElement("span");
      s.textContent = new Date(it.ts).toLocaleString() + " · " + (it.kind === "clean" ? "quick clean" : it.mode) + " · " + fmt(it.text.length) + " chars";
      var load = document.createElement("button"); load.type = "button"; load.className = "btn small"; load.textContent = "Load";
      load.addEventListener("click", function () {
        $("output").value = it.text;
        state.last = { kind: it.kind, origChars: it.origChars, origWords: it.origWords || 0, dup: 0, similar: 0, model: it.model, ms: null, mode: it.mode };
        renderOutputStats(); $("stDup").textContent = "–";
        message("Loaded from history.", "info");
      });
      var del = document.createElement("button"); del.type = "button"; del.className = "btn small danger"; del.textContent = "Delete";
      del.setAttribute("aria-label", "Delete saved result from " + new Date(it.ts).toLocaleString());
      del.addEventListener("click", function () {
        lset(HIST_KEY, JSON.stringify(loadHistory().filter(function (x) { return x.id !== it.id; }))); renderHistory();
      });
      li.appendChild(s); li.appendChild(load); li.appendChild(del); ul.appendChild(li);
    });
  }

  // ---------- wiring ----------
  function init() {
    var m = lget(MODE_KEY, "balanced");
    var radio = document.querySelector('input[name="mode"][value="' + m + '"]');
    if (radio) radio.checked = true;
    $("modeHint").textContent = MODE_HINTS[selectedMode()];
    document.querySelectorAll('input[name="mode"]').forEach(function (r) {
      r.addEventListener("change", function () { lset(MODE_KEY, selectedMode()); $("modeHint").textContent = MODE_HINTS[selectedMode()]; });
    });

    $("input").addEventListener("input", updateInputCounts);
    $("input").addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runCompact(); } });
    $("output").addEventListener("input", renderOutputStats);
    $("compactBtn").addEventListener("click", runCompact);
    $("quickBtn").addEventListener("click", runQuick);
    $("cancelBtn").addEventListener("click", function () { if (state.controller) state.controller.abort(); });
    $("clearInput").addEventListener("click", function () { $("input").value = ""; updateInputCounts(); message(""); $("input").focus(); });
    $("clearOutput").addEventListener("click", function () { $("output").value = ""; state.last = null; setWarnings([]); renderOutputStats(); message(""); });

    $("copyBtn").addEventListener("click", function () { doCopy("plain"); });
    $("copyGpt").addEventListener("click", function () { doCopy("chatgpt"); });
    $("copyClaude").addEventListener("click", function () { doCopy("claude"); });
    $("dlTxt").addEventListener("click", function () { var c = needContext(); if (c) { download("compaction-" + stamp() + ".txt", c + "\n", "text/plain"); message("Downloaded TXT.", "success"); } });
    $("dlMd").addEventListener("click", function () { var c = needContext(); if (c) { download("compaction-" + stamp() + ".md", markdownDoc(c), "text/markdown"); message("Downloaded Markdown.", "success"); } });
    $("dlHandoff").addEventListener("click", function () { var c = needContext(); if (c) { download("compaction-handoff-" + stamp() + ".md", handoff("chatgpt", c) + "\n", "text/markdown"); message("Downloaded AI handoff.", "success"); } });

    $("recheck").addEventListener("click", function () { setPill("Checking Ollama…", "checking"); refresh(); });
    $("modelSelect").addEventListener("change", function () { state.model = $("modelSelect").value; lset(MODEL_KEY, state.model); setRow("rowModel", state.model, "ok"); setPill("Ollama online · " + state.model, "ok"); });
    $("copyPull").addEventListener("click", function () { copyText($("pullCmd").textContent).then(function (ok) { message(ok ? "Command copied." : "Copy was blocked. Select the command and copy it.", ok ? "success" : "error"); }); });
    $("tokenSave").addEventListener("click", function () { var v = $("tokenInput").value.trim(); if (v) { setToken(v); $("tokenInput").value = ""; refresh(); } });
    $("tokenInput").addEventListener("keydown", function (e) { if (e.key === "Enter") $("tokenSave").click(); });

    $("saveToggle").checked = lget(SAVE_KEY, "0") === "1";
    $("saveToggle").addEventListener("change", function () { lset(SAVE_KEY, $("saveToggle").checked ? "1" : "0"); message($("saveToggle").checked ? "Results will now be saved on this device." : "History saving is off. Existing items are kept until you delete them.", "info"); });
    $("clearHistory").addEventListener("click", function () { lremove(HIST_KEY); renderHistory(); message("History deleted.", "success"); });
    renderHistory();

    updateInputCounts(); renderOutputStats();
    refresh();
    setInterval(function () { if (!document.hidden && !state.busy) refresh(); }, 20000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
