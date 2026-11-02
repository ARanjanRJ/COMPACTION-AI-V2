"""A FAKE Ollama server for tests only.

It speaks the same two endpoints the app uses (GET /api/tags, POST /api/chat
with NDJSON streaming) so the real HTTP client code is exercised. It is NOT a
real model: its "summaries" are canned text. Passing tests against it prove our
wiring and error handling, not the quality of a real model's compaction.
"""
import json
import threading
import time

from flask import Flask, Response, jsonify, request
from werkzeug.serving import make_server


class FakeOllama:
    def __init__(self, models=("llama3.2:1b",)):
        self.models = list(models)
        self.required_key = None  # when set, /api/* need "Authorization: Bearer <key>"
        self.last_auth = None
        self.mode = "ok"        # ok | slow | slow_start | error_mid | truncated | garbage | http500 | empty | tags_500 | tags_garbage
        self.delay = 0.0
        self.extra = ""          # extra text appended to every reply (e.g. an invented number)
        self.requests = []
        self.closed = False      # set when our client disconnects mid-stream
        self.app = Flask("fake-ollama")
        self._routes()

    # -- canned reply ------------------------------------------------------
    def reply(self, body):
        user = body["messages"][-1]["content"]
        mode = "?"
        if user.startswith("Mode: "):
            mode = user.split(".", 1)[0][6:]
        first = ""
        for marker in ("<conversation>\n", "<conversation_part>\n", "<notes>\n"):
            if marker in user:
                first = user.split(marker, 1)[1].strip().splitlines()[0][:50]
                break
        if self.mode == "empty":
            return ""
        lines = [
            "## PROJECT / TOPIC", "- topic: %s (mode=%s)" % (first, mode),
            "## KEY FACTS", "- fact noted",
            "## USER PREFERENCES & CONSTRAINTS", "- none stated",
            "## DECISIONS MADE", "- decision noted",
            "## PROGRESS (DONE)", "- done noted",
            "## IN PROGRESS", "- work in progress noted",
            "## PENDING TASKS & NEXT STEPS", "- next step noted",
            "## OPEN QUESTIONS & UNCERTAINTIES", "- none stated",
            "## WARNINGS & LIMITATIONS", "- none stated",
            "## INSTRUCTIONS FOR THE NEXT ASSISTANT", "- continue",
        ]
        if self.extra:
            lines.append(self.extra)
        return "\n".join(lines)

    def _routes(self):
        app = self.app

        @app.get("/api/tags")
        def tags():
            self.last_auth = request.headers.get("Authorization")
            if self.required_key and self.last_auth != "Bearer " + self.required_key:
                return jsonify({"error": "unauthorized"}), 401
            if self.mode == "tags_500":
                return "boom", 500
            if self.mode == "tags_garbage":
                return "not json", 200
            return jsonify({"models": [{"name": m, "model": m} for m in self.models]})

        @app.post("/api/chat")
        def chat():
            self.last_auth = request.headers.get("Authorization")
            if self.required_key and self.last_auth != "Bearer " + self.required_key:
                return jsonify({"error": "unauthorized"}), 401
            body = request.get_json()
            self.requests.append(body)
            if body["model"] not in self.models:
                return jsonify({"error": "model '%s' not found" % body["model"]}), 404
            if self.mode == "http500":
                return jsonify({"error": "boom"}), 500
            if self.mode == "garbage":
                return Response("this is not json\n", mimetype="application/x-ndjson")
            words = self.reply(body).split(" ")

            def gen():
                try:
                    if self.mode == "slow_start":
                        time.sleep(self.delay)
                    for i, w in enumerate(words):
                        if self.mode == "error_mid" and i == 3:
                            yield json.dumps({"error": "out of memory"}) + "\n"
                            return
                        if self.mode == "truncated" and i == 3:
                            return
                        if self.mode == "slow":
                            time.sleep(self.delay)
                        piece = w + (" " if i < len(words) - 1 else "")
                        if piece:
                            yield json.dumps({"message": {"role": "assistant", "content": piece}, "done": False}) + "\n"
                    yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
                except GeneratorExit:
                    self.closed = True
                    raise

            return Response(gen(), mimetype="application/x-ndjson")

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.server.shutdown()
