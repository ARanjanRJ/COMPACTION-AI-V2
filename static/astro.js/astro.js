(function () {
  "use strict";

  const input = document.getElementById("astroInput");
  const send = document.getElementById("astroSend");
  const clear = document.getElementById("astroClear");
  const messagesBox = document.getElementById("astroMessages");
  const status = document.getElementById("astroStatus");

  if (!input || !send || !messagesBox || !status) return;

  const CFG = window.COMPACTION_CONFIG || { apiBase: "" };
  const STORAGE_KEY = "astro6_chat_memory";

  async function loadLongTermMemory() {
    const token = sessionStorage.getItem("compaction_token") || "";
    const headers = {};
    if (token) headers.Authorization = "Bearer " + token;

    const response = await fetch("/api/memories", { headers });
    if (!response.ok) throw new Error("Memory load failed");

    const data = await response.json();
    return data.memories || [];
  }

  async function saveLongTermMemory(content) {
    const token = sessionStorage.getItem("compaction_token") || "";
    const headers = { "Content-Type": "application/json" };

    if (token) headers.Authorization = "Bearer " + token;

    const response = await fetch("/api/memories", {
      method: "POST",
      headers,
      body: JSON.stringify({ content })
    });

    if (!response.ok) throw new Error("Memory save failed");
    return response.json();
  }

  function shouldRemember(text) {
    const patterns = [
      /\bmy project is\b/i,
      /\bi am learning\b/i,
      /\bi'm learning\b/i,
      /\bmy goal is\b/i,
      /\bi prefer\b/i,
      /\bmy career goal\b/i,
      /\bremember\b/i,
      /\bsave this\b/i,
      /என் திட்டம்/i,
      /நான் கற்றுக்கொள்கிறேன்/i,
      /எனக்கு பிடிக்கும்/i,
      /நினைவில் வை/i,
      /nyabagam vechiko/i
    ];

    return patterns.some(pattern => pattern.test(text));
  }

  let messages = [];

  try {
    messages = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    messages = [];
  }

  // ASTRO 6 voice playback
  const speechSupported =
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window;

  function speakReply(text) {
    if (!speechSupported || !text || !text.trim()) return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text.trim());

    utterance.lang = /[\u0B80-\u0BFF]/.test(text)
      ? "ta-IN"
      : "en-IN";

    utterance.rate = 1;
    utterance.pitch = 1;

    utterance.onerror = function (event) {
      if (
        event.error !== "canceled" &&
        event.error !== "interrupted"
      ) {
        status.textContent = "Voice playback unavailable";
      }
    };

    utterance.onend = function () {
      if (status.textContent === "ASTRO 6 is speaking...") {
        status.textContent = "Ready";
      }
    };

    window.speechSynthesis.speak(utterance);
    status.textContent = "ASTRO 6 is speaking...";
  }

  function stopReply() {
    if (speechSupported) {
      window.speechSynthesis.cancel();
      status.textContent = "Voice stopped";
    }
  }

  function addMessage(role, content) {
    const wrap = document.createElement("div");
    wrap.className = "astro-message " + role;

    const label = document.createElement("strong");
    label.textContent = role === "user" ? "You" : "ASTRO 6";

    const body = document.createElement("p");
    body.textContent = content;

    wrap.append(label, body);

    if (role === "assistant") {
      const voiceButton = document.createElement("button");

      voiceButton.type = "button";
      voiceButton.className = "btn";
      voiceButton.textContent = "🔊 Listen";
      voiceButton.setAttribute(
        "aria-label",
        "Listen to ASTRO 6 reply"
      );

      voiceButton.addEventListener("click", function () {
        if (
          speechSupported &&
          window.speechSynthesis.speaking
        ) {
          stopReply();
        } else {
          speakReply(body.textContent);
        }
      });

      wrap.appendChild(voiceButton);
    }

    messagesBox.appendChild(wrap);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    return body;
  }

  function saveMemory() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(messages)
      );
    } catch (error) {
      console.error("Memory save failed", error);
    }
  }

  const memoryList = document.getElementById("astroMemoryList");
  const memoryRefresh = document.getElementById("astroMemoryRefresh");
  const memoryClearAll = document.getElementById("astroMemoryClearAll");

  async function refreshMemories() {
    if (!memoryList) return;

    memoryList.textContent = "Loading memories...";

    try {
      const token = sessionStorage.getItem("compaction_token") || "";
      const headers = {};

      if (token) headers.Authorization = "Bearer " + token;

      const response = await fetch("/api/memories", { headers });

      if (!response.ok) {
        throw new Error("Could not load memories");
      }

      const data = await response.json();
      memoryList.replaceChildren();

      if (!data.memories || !data.memories.length) {
        memoryList.textContent = "No saved memories yet.";
        return;
      }

      data.memories.forEach(function (memory) {
        const item = document.createElement("div");
        item.className = "memory-item";

        const content = document.createElement("p");
        content.textContent = memory.content;

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn danger";
        remove.textContent = "Delete";

        remove.addEventListener("click", async function () {
          if (!confirm("Delete this memory?")) return;

          const result = await fetch(
            "/api/memories/" + memory.id,
            {
              method: "DELETE",
              headers
            }
          );

          if (!result.ok) {
            alert("Memory deletion failed.");
            return;
          }

          refreshMemories();
        });

        item.append(content, remove);
        memoryList.appendChild(item);
      });

    } catch (error) {
      memoryList.textContent = error.message;
    }
  }

  if (memoryRefresh) {
    memoryRefresh.addEventListener("click", refreshMemories);
  }

  if (memoryClearAll) {
    memoryClearAll.addEventListener("click", async function () {
      if (!confirm("Delete ALL saved memories?")) return;

      const token = sessionStorage.getItem("compaction_token") || "";
      const headers = {};

      if (token) headers.Authorization = "Bearer " + token;

      const response = await fetch("/api/memories", {
        method: "DELETE",
        headers
      });

      if (!response.ok) {
        alert("Could not clear memories.");
        return;
      }

      refreshMemories();
    });
  }

  refreshMemories();

  messages.forEach(function (msg) {
    addMessage(msg.role, msg.content);
  });

  async function sendMessage() {
    const text = input.value.trim();

    if (!text || send.disabled) return;

    if (speechSupported) {
      window.speechSynthesis.cancel();
    }

    messages.push({
      role: "user",
      content: text
    });

    saveMemory();
    addMessage("user", text);

    input.value = "";
    send.disabled = true;
    status.textContent = "ASTRO 6 is thinking...";

    const replyElement = addMessage("assistant", "");
    let reply = "";

    try {
      const token = sessionStorage.getItem("compaction_token") || "";

      const headers = {
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson"
      };

      if (token) {
        headers.Authorization = "Bearer " + token;
      }

      if (shouldRemember(text)) {
        await saveLongTermMemory(text);
        await refreshMemories();
        status.textContent = "Memory saved successfully!";
      }

      const response = await fetch(
        (CFG.apiBase || "") + "/api/chat",
        {
          method: "POST",
          headers,
          body: JSON.stringify({ messages })
        }
      );

      if (!response.ok) {
        throw new Error(
          "Request failed: HTTP " + response.status
        );
      }

      if (!response.body || !response.body.getReader) {
        throw new Error("Streaming is not supported.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let buffer = "";
      let completed = false;

      function handleEvent(line) {
        if (!line.trim()) return;

        const event = JSON.parse(line);

        if (event.type === "delta") {
          reply += event.text || "";
          replyElement.textContent = reply;
          messagesBox.scrollTop = messagesBox.scrollHeight;

        } else if (event.type === "error") {
          throw new Error(
            (event.error && event.error.message) ||
            "AI response failed"
          );

        } else if (event.type === "done") {
          completed = true;
        }
      }

      while (true) {
        const result = await reader.read();

        if (result.done) break;

        buffer += decoder.decode(
          result.value,
          { stream: true }
        );

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          handleEvent(line);
        }
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        handleEvent(buffer);
      }

      if (!completed) {
        throw new Error(
          "Connection closed before completion."
        );
      }

      if (!reply.trim()) {
        reply = "I couldn't generate a response. Try again.";
      }

      replyElement.textContent = reply;

      messages.push({
        role: "assistant",
        content: reply
      });

      saveMemory();

      // AUTOMATIC VOICE REPLY
      speakReply(reply);

    } catch (error) {
      replyElement.textContent = "Error: " + error.message;
      status.textContent = "Connection error";

    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  send.addEventListener("click", sendMessage);

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  clear.addEventListener("click", function () {
    if (speechSupported) {
      window.speechSynthesis.cancel();
    }

    messages.length = 0;

    localStorage.removeItem(STORAGE_KEY);
    messagesBox.replaceChildren();

    const welcome = document.createElement("p");

    welcome.textContent =
      "Vanakkam! I'm ASTRO 6. How can I help you?";

    messagesBox.appendChild(welcome);
    status.textContent = "Chat cleared";
  });

})();