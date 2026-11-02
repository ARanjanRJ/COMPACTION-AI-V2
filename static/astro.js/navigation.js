(function () {
  const pages = {
    dashboard: ["Workspace overview", "Your context intelligence command center"],
    astro: ["ASTRO 6", "Your personal AI assistant"],
    compaction: ["Smart Compaction", "Create reusable AI context"],
    voice: ["Voice Agent", "Two-way speech interaction"],
    memory: ["Memory Engine", "Structured conversation memory"],
    accuracy: ["Accuracy Center", "Verify facts before handoff"],
    models: ["AI Model Hub", "Local and optional cloud models"],
    performance: ["Performance Center", "Processing and optimization"],
    history: ["History & Library", "Manage saved results"],
    export: ["Export & Handoff", "Move context between AI assistants"],
    settings: ["Settings & Security", "Privacy and configuration"]
  };

  const nav = document.getElementById("mainNav");

  document.addEventListener("click", function (event) {
    const button = event.target.closest("button[data-page]");
    if (!button) return;

    const key = button.dataset.page;
    if (!pages[key]) return;

    document.querySelectorAll("[data-view]").forEach(function (section) {
      section.hidden = section.dataset.view !== key;
    });

    nav.querySelectorAll("button[data-page]").forEach(function (item) {
      if (item.dataset.page === key) {
        item.setAttribute("aria-current", "page");
      } else {
        item.removeAttribute("aria-current");
      }
    });

    document.getElementById("pageTitle").textContent = pages[key][0];
    document.getElementById("pageSubtitle").textContent = pages[key][1];

    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
