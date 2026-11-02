"""API tests: the real Flask app + real HTTP client code against a FAKE Ollama."""
import json
import logging
import os
import socket
import sys
import threading
import time
import unittest

import requests
from werkzeug.serving import make_server

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import app as appmod  # noqa: E402
import config  # noqa: E402
from fake_ollama import FakeOllama  # noqa: E402

CONVO = ("User: I am building a budget tracker called PennyWise for my family.\n"
         "Assistant: Great, what stack do you want?\n"
         "User: Python and SQLite. The deadline is 14 March and the budget is 5000 rupees.\n"
         "Assistant: Understood. I will keep it simple.\n")
ENV_KEYS = [
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "AI_MODEL",
    "AI_PROVIDER",
    "GROQ_API_KEY",
    "COMPACTION_ACCESS_TOKEN",
    "MAX_INPUT_CHARS",
    "CHUNK_CHARS",
    "MERGE_CHARS",
    "OLLAMA_CONNECT_TIMEOUT",
    "OLLAMA_NUM_CTX",
    "OLLAMA_READ_TIMEOUT",
    "RATE_LIMIT_PER_MINUTE",
    "MAX_CONCURRENT",
    "HOST",
    "CORS_ORIGINS",
    "OLLAMA_API_KEY",
]
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def events(resp):
    return [json.loads(x) for x in resp.get_data(as_text=True).splitlines() if x.strip()]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeOllama().start()

    @classmethod
    def tearDownClass(cls):
        cls.fake.stop()

    def setUp(self):
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ["OLLAMA_BASE_URL"] = self.fake.url
        os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
        self.fake.mode, self.fake.delay, self.fake.extra, self.fake.closed = "ok", 0.0, "", False
        self.fake.models = ["llama3.2:1b"]
        self.fake.requests.clear()
        self.fake.required_key, self.fake.last_auth = None, None
        appmod._hits.clear()
        self.c = appmod.app.test_client()

    def post(self, body, **kw):
        return self.c.post("/api/compact", json=body, **kw)

    # ---- Ollama Cloud (API key) support
    def test_cloud_key_is_sent_and_never_leaked(self):
        self.fake.required_key = "test-key-not-real-123"
        os.environ["OLLAMA_API_KEY"] = "test-key-not-real-123"
        st = self.c.get("/api/status")
        d = st.get_json()
        self.assertTrue(d["cloud"] and d["ollama"]["reachable"])
        self.assertNotIn("test-key-not-real-123", st.get_data(as_text=True))
        r = self.post({"text": CONVO, "mode": "short"})
        self.assertEqual(events(r)[-1]["type"], "result")
        self.assertEqual(self.fake.last_auth, "Bearer test-key-not-real-123")
        self.assertNotIn("test-key-not-real-123", r.get_data(as_text=True))

    def test_cloud_wrong_key_gives_clear_error(self):
        self.fake.required_key = "right-key-0000000000"
        os.environ["OLLAMA_API_KEY"] = "wrong-key-0000000000"
        d = self.c.get("/api/status").get_json()
        self.assertFalse(d["ollama"]["reachable"])
        self.assertEqual(d["ollama"]["error"]["code"], "ollama_auth")
        r = self.post({"text": CONVO, "mode": "short"})
        self.assertEqual(r.get_json()["error"]["code"], "ollama_auth")

    def test_no_key_means_no_auth_header_and_cloud_false(self):
        d = self.c.get("/api/status").get_json()
        self.assertFalse(d["cloud"])
        self.assertIsNone(self.fake.last_auth)

    def test_key_refused_over_plain_http(self):
        os.environ["OLLAMA_API_KEY"] = "some-key-0000000000"
        os.environ["OLLAMA_BASE_URL"] = "http://example.com"
        with self.assertRaises(RuntimeError):
            config.startup_check(config.get())

    # ---- startup / status
    def test_health(self):
        d = self.c.get("/api/health").get_json()
        self.assertEqual((d["ok"], d["app"], d["authRequired"]), (True, "compaction", False))

    def test_index_and_static_served(self):
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_status_reachable_lists_real_models(self):
        d = self.c.get("/api/status").get_json()
        self.assertTrue(d["ollama"]["reachable"])
        self.assertEqual(d["ollama"]["models"], ["llama3.2:1b"])
        self.assertTrue(d["model"]["defaultInstalled"])

    def test_status_default_model_missing(self):
        self.fake.models = ["other:7b"]
        d = self.c.get("/api/status").get_json()
        self.assertFalse(d["model"]["defaultInstalled"])

    def test_status_ollama_down(self):
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:%d" % free_port()
        d = self.c.get("/api/status").get_json()
        self.assertFalse(d["ollama"]["reachable"])
        self.assertEqual(d["ollama"]["error"]["code"], "ollama_unavailable")

    def test_status_bad_tags_responses(self):
        for mode, code in (("tags_500", "ollama_error"), ("tags_garbage", "bad_response")):
            self.fake.mode = mode
            self.assertEqual(self.c.get("/api/status").get_json()["ollama"]["error"]["code"], code, mode)

    # ---- validation
    def test_empty_and_short_input(self):
        for body, code in (({"text": ""}, "empty_input"), ({"text": "   \n "}, "empty_input"), ({}, "empty_input"),
                           ({"text": "hi"}, "too_short")):
            r = self.post(body)
            self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (400, code), body)

    def test_not_json(self):
        self.assertEqual(self.c.post("/api/compact", data="x", content_type="application/json").status_code, 400)

    def test_too_long(self):
        os.environ["MAX_INPUT_CHARS"] = "100"
        r = self.post({"text": "x" * 101})
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (413, "too_long"))

    def test_bad_mode_and_model_name(self):
        self.assertEqual(self.post({"text": CONVO, "mode": "extreme"}).status_code, 400)
        self.assertEqual(self.post({"text": CONVO, "model": "a b; rm -rf /"}).status_code, 400)

    def test_model_missing(self):
        r = self.post({"text": CONVO, "model": "nope:1b"})
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (404, "model_missing"))
        self.assertIn("ollama pull nope:1b", r.get_json()["error"]["message"])

    def test_ollama_unavailable(self):
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:%d" % free_port()
        r = self.post({"text": CONVO})
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (503, "ollama_unavailable"))

    # ---- success paths
    def test_successful_compaction(self):
        r = self.post({"text": CONVO, "mode": "balanced"})
        self.assertEqual(r.status_code, 200)
        ev = events(r)
        kinds = [e["type"] for e in ev]
        self.assertEqual((kinds[0], kinds[-1]), ("stage", "result"))
        self.assertTrue(set(kinds[1:-1]) <= {"progress"})
        res = ev[-1]
        self.assertTrue(res["context"].startswith("## PROJECT / TOPIC"))
        self.assertTrue(res["stats"]["format_ok"])
        self.assertEqual(res["stats"]["original_chars"], len(CONVO.strip()))
        sent = self.fake.requests[0]
        self.assertEqual(sent["model"], "llama3.2:1b")
        self.assertTrue(sent["stream"])
        self.assertIn("Never invent", sent["messages"][0]["content"])
        self.assertIn("PennyWise", sent["messages"][1]["content"])
        self.assertEqual(sent["options"]["num_ctx"], 4096)

    def test_modes_change_what_is_sent(self):
        budgets = {}
        for mode in ("short", "balanced", "detailed"):
            self.fake.requests.clear()
            self.post({"text": CONVO, "mode": mode}).get_data()
            budgets[mode] = self.fake.requests[0]["options"]["num_predict"]
            self.assertTrue(self.fake.requests[0]["messages"][1]["content"].startswith("Mode: " + mode.capitalize()))
        self.assertLess(budgets["short"], budgets["balanced"])
        self.assertLess(budgets["balanced"], budgets["detailed"])

    def test_selected_installed_model_is_used(self):
        self.fake.models = ["llama3.2:1b", "qwen2.5:0.5b"]
        self.post({"text": CONVO, "model": "qwen2.5:0.5b"}).get_data()
        self.assertEqual(self.fake.requests[0]["model"], "qwen2.5:0.5b")

    def test_long_conversation_is_chunked(self):
        os.environ["CHUNK_CHARS"] = "400"
        text = "\n".join("User: message %d about topic %d with a few extra words here." % (i, i * 13) for i in range(60))
        ev = events(self.post({"text": text}))
        self.assertEqual(ev[-1]["type"], "result")
        self.assertGreater(ev[-1]["stats"]["chunks"], 3)
        self.assertGreater(len(self.fake.requests), ev[-1]["stats"]["chunks"])
        self.assertTrue(any(e["type"] == "progress" for e in ev))

    def test_duplicates_reported_and_not_sent(self):
        dup = "User: please remember that the invoice number is ABC-123 and must not change."
        text = "\n".join([dup] * 4 + ["Assistant: noted, I will keep it exactly as is."])
        ev = events(self.post({"text": text}))
        self.assertEqual(ev[0]["duplicates_removed"], 3)
        self.assertEqual(self.fake.requests[0]["messages"][1]["content"].count("ABC-123"), 1)

    def test_invented_number_is_flagged(self):
        self.fake.extra = "- team size 424242"
        ev = events(self.post({"text": CONVO}))
        self.assertIn("424242", ev[-1]["stats"]["unverified_numbers"])

    # ---- model / stream failures (reported as a final error event)
    def test_stream_failures(self):
        cases = {"error_mid": "ollama_error", "garbage": "bad_response", "truncated": "bad_response",
                 "http500": "ollama_error", "empty": "empty_response"}
        for mode, code in cases.items():
            self.fake.mode = mode
            ev = events(self.post({"text": CONVO}))
            self.assertEqual(ev[-1]["type"], "error", mode)
            self.assertEqual(ev[-1]["error"]["code"], code, mode)

    def test_timeout(self):
        self.fake.mode, self.fake.delay = "slow_start", 1.5
        os.environ["OLLAMA_READ_TIMEOUT"] = "0.3"
        ev = events(self.post({"text": CONVO}))
        self.assertEqual(ev[-1]["error"]["code"], "ollama_timeout")

    # ---- access control / abuse limits
    def test_access_token(self):
        os.environ["COMPACTION_ACCESS_TOKEN"] = "x" * 20
        self.assertTrue(self.c.get("/api/health").get_json()["authRequired"])
        self.assertEqual(self.c.get("/api/status").status_code, 401)
        self.assertEqual(self.post({"text": CONVO}).status_code, 401)
        bad = {"Authorization": "Bearer " + "y" * 20}
        self.assertEqual(self.post({"text": CONVO}, headers=bad).status_code, 401)
        good = {"Authorization": "Bearer " + "x" * 20}
        self.assertEqual(self.c.get("/api/status", headers=good).status_code, 200)
        self.assertEqual(self.post({"text": CONVO}, headers=good).status_code, 200)

    def test_rate_limit(self):
        os.environ["RATE_LIMIT_PER_MINUTE"] = "3"
        codes = [self.c.get("/api/status").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[-1], 429)

    def test_only_one_compaction_at_a_time(self):
        slot = appmod._get_slots()
        self.assertTrue(slot.acquire(blocking=False))
        try:
            r = self.post({"text": CONVO})
            self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (429, "busy"))
        finally:
            slot.release()
        self.assertEqual(self.post({"text": CONVO}).status_code, 200)

    def test_security_headers_and_cors(self):
        r = self.c.get("/")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        r = self.c.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)
        os.environ["CORS_ORIGINS"] = "https://me.example"
        r = self.c.get("/api/health", headers={"Origin": "https://me.example"})
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], "https://me.example")

    def test_startup_check(self):
        c = config.get()
        c.host, c.token = "0.0.0.0", ""
        with self.assertRaises(RuntimeError):
            config.startup_check(c)
        c.token = "short"
        with self.assertRaises(RuntimeError):
            config.startup_check(c)
        c.token = "z" * 20
        config.startup_check(c)
        c.host, c.token = "127.0.0.1", ""
        config.startup_check(c)

    # ---- privacy
    def test_conversation_text_is_never_logged(self):
        secret = "ZEBRA-SECRET-7731"
        records = []

        class H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = H(level=logging.DEBUG)
        root = logging.getLogger()
        old = root.level
        root.addHandler(h)
        root.setLevel(logging.DEBUG)
        try:
            self.post({"text": CONVO + "User: my code word is %s and that is all.\n" % secret}).get_data()
            self.fake.mode = "http500"
            self.post({"text": CONVO + secret}).get_data()
        finally:
            root.removeHandler(h)
            root.setLevel(old)
        self.assertFalse([m for m in records if secret in m])


class CancelTest(unittest.TestCase):
    """Closing the browser connection must stop Ollama and free the slot."""

    def test_cancel_stops_generation_and_frees_slot(self):
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        fake = FakeOllama().start()
        fake.mode, fake.delay = "slow", 0.05
        os.environ["OLLAMA_BASE_URL"] = fake.url
        os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
        appmod._hits.clear()
        server = make_server("127.0.0.1", 0, appmod.app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % server.server_port
        try:
            r = requests.post(base + "/api/compact", json={"text": CONVO * 3}, stream=True, timeout=10)
            self.assertEqual(r.status_code, 200)
            first = next(r.iter_lines())
            self.assertIn(b"stage", first)
            r.close()  # the user pressed Cancel
            deadline = time.time() + 8
            while time.time() < deadline and not fake.closed:
                time.sleep(0.1)
            self.assertTrue(fake.closed, "Ollama connection was not closed after the browser cancelled")
            fake.mode, fake.delay = "ok", 0
            time.sleep(0.3)
            r2 = requests.post(base + "/api/compact", json={"text": CONVO}, timeout=10)
            self.assertEqual(r2.status_code, 200)  # slot was released, not stuck on 'busy'
        finally:
            server.shutdown()
            fake.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
