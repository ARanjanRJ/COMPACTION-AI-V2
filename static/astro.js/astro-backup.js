
(function () {
  "use strict";

  const input = document.getElementById("astroInput");
  const send = document.getElementById("astroSend");
  const clear = document.getElementById("astroClear");
  const messagesBox = document.getElementById("astroMessages");
  const status = document.getElementById("astroStatus");

  if (!input || !send || !messagesBox || !status) return;

  const CFG = window.COMPACTION_CONFIG || { apiBase: "" };
  const messages = [];

  function addMessage(role, content) {
    const wrap = document.createElement("div");
    wrap.className = "astro-message " + role;

    const label = document.createElement("strong");
    label.textContent = role === "user" ? "You" : "ASTRO 6";

    const body = document.createElement("p");
    body.textContent = content;

    wrap.append(label, body);
    messagesBox.appendChild(wrap);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    return body;
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || send.disabled) return;

    messages.push({ role: "user", content: text });
    addMessage("user", text);
    input.value = "";
    send.disabled = true;
    status.textContent = "ASTRO 6 is thinking...";

    const replyElement = addMessage("assistant", "");
    let reply = "";

    try {
      const token = sessionStorage.getItem("compaction_token") || "";
      const headers = { "Content-Type": "application/json" };

      if (token) headers.Authorization = "Bearer " + token;

      const response = await fetch(
        (CFG.apiBase || "") + "/api/chat",
        {
          method: "POST",
          headers,
          body: JSON.stringify({ messages }),
        }
      );

      if (!response.ok) {
        throw new Error("Request failed: HTTP " + response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let completed = false;

      while (true) {
        const result = await reader.read();
        if (result.done) break;

        buffer += decoder.decode(result.value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;

          const event = JSON.parse(line);

          if (event.type === "delta") {
            reply += event.text || "";
            replyElement.textContent = reply;
            messagesBox.scrollTop = messagesBox.scrollHeight;
          } else if (event.type === "error") {
            throw new Error(event.error || "AI response failed");
          } else if (event.type === "done") {
            completed = true;
          }
        }
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        const event = JSON.parse(buffer);
        if (event.type === "delta") {
          reply += event.text || "";
          replyElement.textContent = reply;
        } else if (event.type === "error") {
          throw new Error(event.error || "AI response failed");
        } else if (event.type === "done") {
          completed = true;
        }
      }

      if (!completed) throw new Error("Connection closed before completion.");
      if (!reply.trim()) reply = "I couldn't generate a response. Try again.";

      replyElement.textContent = reply;
      messages.push({ role: "assistant", content: reply });
      status.textContent = "Ready";

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
    messages.length = 0;
    messagesBox.replaceChildren();
    const welcome = document.createElement("p");
    welcome.textContent = "Vanakkam! I'm ASTRO 6. How can I help you?";
    messagesBox.appendChild(welcome);
    status.textContent = "Chat cleared";
  });
})();
