// Where the COMPACTION backend lives.
// "" means "the same server that served this page" (the normal case).
// If you host this frontend separately (e.g. GitHub Pages), put your backend's
// https address here, for example "https://compaction.example.com", and add the
// frontend's address to CORS_ORIGINS in the backend's .env.
window.COMPACTION_CONFIG = { apiBase: "" };
