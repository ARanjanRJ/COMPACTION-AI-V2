/* COMPACTION AI V2 - Memory Engine UI */
(function () {
  "use strict";

  var TOKEN_KEY = "compaction_token";
  var $ = function (id) { return document.getElementById(id); };

  function authHeaders(extra) {
    var headers = extra || {};
    try {
      var token = window.sessionStorage.getItem(TOKEN_KEY);
      if (token) headers.Authorization = "Bearer " + token;
    } catch (e) { /* session storage may be unavailable */ }
    return headers;
  }

  function setStatus(message, kind) {
    var status = $("memoryEngineStatus");
    if (!status) return;
    status.textContent = message;
    status.dataset.kind = kind || "info";
  }

  async function api(path, options) {
    var response = await fetch(path, Object.assign({ cache: "no-store" }, options || {}));
    var data;
    try { data = await response.json(); } catch (e) { data = {}; }
    if (response.status === 401) {
      throw new Error("Access token required. Open Compaction and unlock with your backend token, then return here.");
    }
    if (!response.ok || data.ok === false) {
      var detail = data.error && data.error.message ? data.error.message : "Request failed (HTTP " + response.status + ").";
      throw new Error(detail);
    }
    return data;
  }

  function renderMemories(items) {
    var list = $("memoryEngineList");
    var count = $("memoryEngineCount");
    if (!list) return;
    list.replaceChildren();
    count.textContent = String(items.length);

    if (!items.length) {
      var empty = document.createElement("p");
      empty.className = "note";
      empty.textContent = "No saved memories yet. Add a fact or preference above.";
      list.appendChild(empty);
      return;
    }

    items.forEach(function (item) {
      var card = document.createElement("article");
      card.className = "feature-card memory-entry";

      var content = document.createElement("p");
      content.textContent = item.content || "";
      card.appendChild(content);

      var meta = document.createElement("p");
      meta.className = "note";
      meta.textContent = item.created_at ? "Saved · " + item.created_at : "Saved memory";
      card.appendChild(meta);

      var actions = document.createElement("div");
      actions.className = "row";
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn danger";
      remove.textContent = "Delete";
      remove.dataset.deleteMemory = String(item.id);
      actions.appendChild(remove);
      card.appendChild(actions);
      list.appendChild(card);
    });
  }

  async function refreshMemories() {
    setStatus("Loading saved memories…", "info");
    try {
      var data = await api("/api/memories", {
        headers: authHeaders()
      });
      renderMemories(Array.isArray(data.memories) ? data.memories : []);
      setStatus("Memory Engine connected. Memories are stored in your local SQLite database.", "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  async function saveMemory(event) {
    event.preventDefault();
    var input = $("memoryEngineInput");
    var content = input.value.trim();
    if (!content) {
      setStatus("Enter a memory before saving.", "error");
      input.focus();
      return;
    }
    if (content.length > 2000) {
      setStatus("Memory must be 2,000 characters or fewer.", "error");
      return;
    }

    var save = $("memoryEngineSave");
    save.disabled = true;
    setStatus("Saving memory…", "info");
    try {
      await api("/api/memories", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ content: content })
      });
      input.value = "";
      await refreshMemories();
      setStatus("Memory saved successfully.", "success");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      save.disabled = false;
    }
  }

  async function deleteMemory(id) {
    if (!window.confirm("Delete this saved memory?")) return;
    try {
      await api("/api/memories/" + encodeURIComponent(id), {
        method: "DELETE",
        headers: authHeaders()
      });
      await refreshMemories();
      setStatus("Memory deleted.", "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  async function clearAllMemories() {
    if (!window.confirm("Delete ALL saved memories? This cannot be undone.")) return;
    try {
      await api("/api/memories", {
        method: "DELETE",
        headers: authHeaders()
      });
      await refreshMemories();
      setStatus("All memories cleared.", "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function init() {
    var form = $("memoryEngineForm");
    if (!form) return;
    form.addEventListener("submit", saveMemory);
    $("memoryEngineRefresh").addEventListener("click", refreshMemories);
    $("memoryEngineClearAll").addEventListener("click", clearAllMemories);
    $("memoryEngineList").addEventListener("click", function (event) {
      var button = event.target.closest("[data-delete-memory]");
      if (button) deleteMemory(button.dataset.deleteMemory);
    });
    refreshMemories();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
