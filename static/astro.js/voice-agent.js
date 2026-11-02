/* =========================================================
   COMPACTION AI V2 — ASTRO 6 VOICE AGENT (FINAL)
   Browser Speech Recognition + /api/chat NDJSON + Browser TTS
   Preserves existing Voice Agent UI hooks and API contract.
========================================================= */

(() => {
  "use strict";

  const voicePage = document.querySelector('[data-view="voice"]');
  if (!voicePage || voicePage.dataset.voiceReady === "true") return;
  voicePage.dataset.voiceReady = "true";

  const CFG = window.COMPACTION_CONFIG || {};
  const API_BASE = typeof CFG.apiBase === "string" ? CFG.apiBase.replace(/\/$/, "") : "";
  const TOKEN_KEY = "compaction_token";
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

  /* =====================================================
     VOICE AGENT INTERFACE
  ===================================================== */

  voicePage.innerHTML = `
    <div class="va-shell">
      <header class="va-head">
        <div>
          <div class="va-kicker">COMPACTION AI · ASTRO 6</div>
          <h2>Voice conversation</h2>
          <p class="va-sub">Speak naturally in Tamil or English. ASTRO will listen and reply.</p>
        </div>
        <span class="va-state" id="va-status" role="status" aria-live="polite">READY</span>
      </header>
      <section class="va-card">
        <div class="va-orb" id="va-orb" aria-hidden="true">◉</div>
        <div class="va-center">
          <h3>Talk with ASTRO 6</h3>
          <p>Press Start speaking, wait for Listening, then speak clearly at your normal pace.</p>
        </div>
        <div class="va-toolbar">
          <select id="va-language" aria-label="Speech language">
            <option value="ta-IN">Tamil</option>
            <option value="en-IN">English (India)</option>
          </select>
          <button class="primary" id="va-start" type="button">🎙 Start speaking</button>
          <button id="va-stop" type="button" disabled>Stop listening</button>
          <button id="va-repeat" type="button" disabled>🔊 Repeat reply</button>
          <button id="va-mute" type="button">Stop voice</button>
        </div>
        <div class="va-panels">
          <div class="va-pane"><h4>YOU SAID</h4><div class="va-text" id="va-transcript">Your speech will appear here.</div></div>
          <div class="va-pane"><h4>ASTRO 6</h4><div class="va-text" id="va-reply">Vanakkam! I am ready.</div></div>
        </div>
        <p class="va-foot" id="va-hint">Microphone permission is required. Keep this page open while speaking.</p>
      </section>
    </div>`;

  /* =====================================================
     ELEMENT REFERENCES
  ===================================================== */

  const $ = id => voicePage.querySelector(`#${id}`);
  const startBtn = $("va-start");
  const stopBtn = $("va-stop");
  const repeatBtn = $("va-repeat");
  const status = $("va-status");
  const orb = $("va-orb");
  const transcriptBox = $("va-transcript");
  const replyBox = $("va-reply");
  const hint = $("va-hint");

  /* =====================================================
     STATE
  ===================================================== */

  let recognition = null;
  let listening = false;
  let busy = false;
  let lastReply = "";
  let requestController = null;
  let finalTranscript = "";
  let intentionalStop = false;
  let voicesReady = false;
  let availableVoices = [];

  function setStatus(label, active = false) {
    status.textContent = label.toUpperCase();
    orb.classList.toggle("active", active);
  }

  /* =====================================================
     AUTHENTICATION
  ===================================================== */

  function authHeaders() {
    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/x-ndjson"
    };

    try {
      const token = sessionStorage.getItem(TOKEN_KEY);
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch (_) {
      console.warn("ASTRO: session storage unavailable.");
    }

    return headers;
  }

  function parseErrorPayload(payload, fallback) {
    if (payload && payload.error && typeof payload.error.message === "string") {
      return payload.error.message;
    }

    if (payload && typeof payload.message === "string") {
      return payload.message;
    }

    return fallback;
  }

  /* =====================================================
     LANGUAGE DETECTION
  ===================================================== */

  function languageFor(text) {
    return /[\u0B80-\u0BFF]/.test(text) ? "ta-IN" : "en-IN";
  }

  /* =====================================================
     VOICE SELECTION
  ===================================================== */

  function loadVoices() {
    if (!canSpeak) return;
    availableVoices = window.speechSynthesis.getVoices() || [];
    voicesReady = availableVoices.length > 0;
  }

  if (canSpeak) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }

  function chooseVoice(lang) {
    if (!voicesReady) loadVoices();

    const prefix = lang.toLowerCase().split("-")[0];

    return availableVoices.find(
      v => v.lang && v.lang.toLowerCase() === lang.toLowerCase()
    ) || availableVoices.find(
      v => v.lang && v.lang.toLowerCase().startsWith(prefix)
    ) || null;
  }

  /* =====================================================
     TEXT TO SPEECH
  ===================================================== */

  function speak(text) {
    if (!text) return;

    if (!canSpeak) {
      hint.textContent = "Speech playback is not supported by this browser.";
      setStatus("Text ready");
      return;
    }

    window.speechSynthesis.cancel();

    const lang = languageFor(text);
    const utterance = new SpeechSynthesisUtterance(text);
    const voice = chooseVoice(lang);

    utterance.lang = lang;

    if (voice) utterance.voice = voice;

    utterance.rate = 0.82;
    utterance.pitch = 1;
    utterance.volume = 1;

    utterance.onstart = () => setStatus("ASTRO speaking", true);

    utterance.onend = () => {
      setStatus("Ready");
      if (!busy && recognition) startBtn.disabled = false;
    };

    utterance.onerror = event => {
      if (event.error !== "canceled" && event.error !== "interrupted") {
        setStatus("Voice playback error");
        hint.textContent = "ASTRO reply is ready as text, but browser speech playback failed. Check Windows output volume.";
      }
    };

    window.speechSynthesis.speak(utterance);
  }

  /* =====================================================
     MICROPHONE CHECK
  ===================================================== */

  async function checkMicrophone() {
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      throw new Error("Microphone access needs localhost or HTTPS. Open ASTRO from http://127.0.0.1:5000.");
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const tracks = stream.getAudioTracks();

    const usable = tracks.some(
      track => track.readyState === "live" && track.enabled
    );

    tracks.forEach(track => track.stop());

    if (!usable) {
      throw new Error("No active microphone input was found. Check Windows Sound > Input.");
    }
  }

  /* =====================================================
     SEND MESSAGE TO ASTRO 6
  ===================================================== */

  async function sendToAstro(userText) {
    if (!userText || busy) return;

    busy = true;
    requestController = new AbortController();

    startBtn.disabled = true;
    repeatBtn.disabled = true;

    replyBox.textContent = "ASTRO 6 is thinking…";
    setStatus("Thinking", true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          messages: [
            {
              role: "user",
              content: userText
            }
          ]
        }),
        signal: requestController.signal
      });

      if (!response.ok) {
        let message = `Request failed (HTTP ${response.status}).`;

        try {
          message = parseErrorPayload(await response.json(), message);
        } catch (_) {}

        throw new Error(message);
      }

      if (!response.body || typeof response.body.getReader !== "function") {
        throw new Error("Streaming response is not supported by this browser.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let answer = "";
      let completed = false;

      const handleLine = line => {
        if (!line.trim()) return;

        let packet;

        try {
          packet = JSON.parse(line);
        } catch (_) {
          throw new Error("ASTRO returned an invalid response packet.");
        }

        if (packet.type === "delta") {
          answer += typeof packet.text === "string" ? packet.text : "";
          replyBox.textContent = answer;
        }

        else if (packet.type === "error") {
          throw new Error(
            parseErrorPayload(packet, "ASTRO response failed.")
          );
        }

        else if (packet.type === "done") {
          completed = true;
        }
      };

      while (true) {
        const part = await reader.read();

        if (part.done) break;

        buffer += decoder.decode(part.value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          handleLine(line);
        }
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        handleLine(buffer);
      }

      if (!completed) {
        throw new Error("Connection ended before ASTRO finished replying.");
      }

      lastReply = answer.trim();

      replyBox.textContent =
        lastReply || "ASTRO returned an empty response.";

      repeatBtn.disabled = !lastReply;

      if (lastReply) {
        speak(lastReply);
      } else {
        setStatus("Ready");
      }

    } catch (error) {
      if (error.name === "AbortError") {
        replyBox.textContent = "Voice response stopped.";
        setStatus("Stopped");
      } else {
        replyBox.textContent = `Error: ${error.message}`;
        hint.textContent = error.message;
        setStatus("Connection error");
        console.error("ASTRO Voice Error:", error);
      }

    } finally {
      busy = false;
      requestController = null;
      stopBtn.disabled = true;
      listening = false;

      if (!canSpeak || !window.speechSynthesis.speaking) {
        orb.classList.remove("active");
        startBtn.disabled = !recognition;

        if (status.textContent === "THINKING") {
          setStatus("Ready");
        }
      }
    }
  }

  /* =====================================================
     SPEECH RECOGNITION SUPPORT
  ===================================================== */

  if (!SpeechRecognition) {
    startBtn.disabled = true;
    setStatus("Speech recognition unavailable");
    hint.textContent = "Chrome speech recognition is unavailable. Use the latest Google Chrome browser.";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  /* =====================================================
     MICROPHONE START
  ===================================================== */

  recognition.onstart = () => {
    listening = true;
    intentionalStop = false;
    finalTranscript = "";

    startBtn.disabled = true;
    stopBtn.disabled = false;

    setStatus("Listening", true);

    transcriptBox.textContent = "Listening… Speak now.";

    hint.textContent = "Listening is active. Speak at your normal pace; tap Stop listening when finished if needed.";
  };

  /* =====================================================
     SPEECH RESULT
  ===================================================== */

  recognition.onresult = event => {
    let interim = "";

    for (
      let i = event.resultIndex;
      i < event.results.length;
      i += 1
    ) {
      const text =
        event.results[i][0] && event.results[i][0].transcript
          ? event.results[i][0].transcript
          : "";

      if (event.results[i].isFinal) {
        finalTranscript += text;
      } else {
        interim += text;
      }
    }

    const visible = (finalTranscript + " " + interim).trim();

    transcriptBox.textContent = visible || "Listening…";

    if (finalTranscript.trim()) {
      const message = finalTranscript.trim();

      transcriptBox.textContent = message;

      try {
        recognition.stop();
      } catch (_) {}

      sendToAstro(message);
    }
  };

  /* =====================================================
     MICROPHONE ERROR
  ===================================================== */

  recognition.onerror = event => {
    const messages = {
      "not-allowed": "Microphone permission is blocked. Allow Microphone for this localhost site in Chrome site settings, then reload.",
      "service-not-allowed": "Chrome speech recognition service is blocked by the browser or network.",
      "no-speech": "Chrome did not detect speech. Check the selected Windows input device and speak after LISTENING appears.",
      "audio-capture": "No microphone input is available. Check Windows Settings > System > Sound > Input.",
      "network": "Chrome speech recognition needs an internet connection.",
      "aborted": "Listening stopped. Press Start speaking to try again."
    };

    hint.textContent =
      messages[event.error] ||
      `Speech recognition error: ${event.error}.`;

    listening = false;
    stopBtn.disabled = true;

    if (!busy) {
      startBtn.disabled = false;
    }

    setStatus(
      event.error === "no-speech" || event.error === "aborted"
        ? "Ready"
        : "Microphone error"
    );

    console.warn("ASTRO Speech Recognition:", event.error);
  };

  /* =====================================================
     MICROPHONE STOP
  ===================================================== */

  recognition.onend = () => {
    listening = false;
    stopBtn.disabled = true;

    if (
      !busy &&
      !(canSpeak && window.speechSynthesis.speaking)
    ) {
      startBtn.disabled = false;

      if (status.textContent === "LISTENING") {
        setStatus("Ready");
      }
    }
  };

  /* =====================================================
     START SPEAKING BUTTON
  ===================================================== */

  startBtn.addEventListener("click", async () => {
    if (busy || listening) return;

    if (canSpeak) {
      window.speechSynthesis.cancel();
    }

    startBtn.disabled = true;
    setStatus("Checking microphone");

    hint.textContent = "Checking microphone permission…";

    try {
      await checkMicrophone();

      recognition.lang = $("va-language").value;

      recognition.start();

    } catch (error) {
      startBtn.disabled = false;
      setStatus("Microphone unavailable");

      hint.textContent =
        error.name === "NotAllowedError" ||
        error.name === "PermissionDeniedError"
          ? "Microphone permission denied. Allow it in Chrome site settings and Windows microphone privacy settings."
          : error.message ||
            "Microphone could not start. Check Windows Sound > Input.";

      console.error("ASTRO microphone setup:", error);
    }
  });

  /* =====================================================
     STOP LISTENING BUTTON
  ===================================================== */

  stopBtn.addEventListener("click", () => {
    if (!recognition || !listening) return;

    intentionalStop = true;

    try {
      recognition.stop();
    } catch (_) {}
  });

  /* =====================================================
     REPEAT REPLY BUTTON
  ===================================================== */

  repeatBtn.addEventListener("click", () => {
    if (lastReply) {
      speak(lastReply);
    }
  });

  /* =====================================================
     STOP VOICE BUTTON
  ===================================================== */

  $("va-mute").addEventListener("click", () => {
    if (canSpeak) {
      window.speechSynthesis.cancel();
    }

    if (requestController) {
      requestController.abort();
    }

    if (recognition && listening) {
      intentionalStop = true;

      try {
        recognition.abort();
      } catch (_) {}
    }

    listening = false;
    stopBtn.disabled = true;
    startBtn.disabled = !busy ? false : true;

    setStatus("Voice stopped");
  });

})();