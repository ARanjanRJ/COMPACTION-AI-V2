"""COMPACTION backend with Ollama-local and Groq-cloud providers."""

import hmac
import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import compactor
import config
import ollama_client
import groq_client
import memory_store

from ollama_client import OllamaError


VERSION = "2.1.0"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/\-]{1,100}$")

app = Flask(__name__, static_folder=None)

memory_store.initialize()
config.startup_check(config.get())

_hits = defaultdict(deque)
_slots = None
_slots_size = None


def _get_slots():
    global _slots, _slots_size

    size = config.get().max_concurrent

    if _slots is None or _slots_size != size:
        _slots = threading.BoundedSemaphore(size)
        _slots_size = size

    return _slots


def err(code, message, status):
    return jsonify({
        "ok": False,
        "error": {
            "code": code,
            "message": message
        }
    }), status


def rate_limited(ip):
    limit = config.get().rate_limit_per_minute
    now = time.time()
    q = _hits[ip]

    while q and now - q[0] > 60:
        q.popleft()

    if len(q) >= limit:
        return True

    q.append(now)
    return False


def authorized():
    token = config.get().token

    if not token:
        return True

    header = request.headers.get("Authorization", "")
    given = header[7:] if header.startswith("Bearer ") else ""

    return hmac.compare_digest(
        given.encode(),
        token.encode()
    )


@app.before_request
def guard():
    if not request.path.startswith("/api/") or request.method == "OPTIONS":
        return None

    if request.path != "/api/health" and not authorized():
        return err(
            "unauthorized",
            "A valid access token is required.",
            401
        )

    if rate_limited(request.remote_addr or "?"):
        return err(
            "rate_limited",
            "Too many requests. Wait a minute and try again.",
            429
        )

    cfg = config.get()

    if request.content_length and request.content_length > cfg.max_input_chars * 4 + 10_000:
        return err(
            "too_large",
            "Request is too large.",
            413
        )

    return None


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"

    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )

    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"

        origin = request.headers.get("Origin", "").rstrip("/")

        if origin and origin in config.get().cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )
            resp.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, DELETE, OPTIONS"
            )

    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def preflight(_any):
    return ("", 204)


@app.get("/api/health")
def health():
    cfg = config.get()

    return jsonify({
        "ok": True,
        "app": "compaction",
        "version": VERSION,
        "provider": cfg.provider,
        "authRequired": bool(cfg.token)
    })


def provider_models(cfg):
    if cfg.provider == "groq":
        return groq_client.list_models(
            cfg.groq_api_key,
            cfg.connect_timeout
        )

    return ollama_client.list_models(
        cfg.ollama_base,
        cfg.connect_timeout,
        api_key=cfg.api_key
    )


@app.get("/api/status")
def status():
    cfg = config.get()

    info = {
        "reachable": False,
        "models": [],
        "error": None
    }

    try:
        models = provider_models(cfg)
        info.update(
            reachable=True,
            models=models
        )

    except (OllamaError, groq_client.GroqError) as e:
        info["error"] = {
            "code": e.code,
            "message": e.message
        }

    selected_available = cfg.model in info["models"]

    return jsonify({
        "ok": True,
        "version": VERSION,
        "provider": cfg.provider,

        "ollama": info if cfg.provider == "ollama" else {
            "reachable": False,
            "models": [],
            "error": None
        },

        "groq": info if cfg.provider == "groq" else {
            "reachable": False,
            "models": [],
            "error": None
        },

        "cloud": cfg.provider == "groq" or bool(cfg.api_key),

        "model": {
            "default": cfg.model,
            "defaultInstalled": selected_available
        },

        "modes": {
            k: v["label"]
            for k, v in compactor.MODES.items()
        },

        "limits": {
            "maxInputChars": cfg.max_input_chars,
            "chunkChars": cfg.chunk_chars
        }
    })


@app.post("/api/compact")
def compact_route():
    cfg = config.get()

    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return err(
            "bad_request",
            "Request body must be JSON.",
            400
        )

    text = body.get("text")

    if not isinstance(text, str) or not text.strip():
        return err(
            "empty_input",
            "Paste a conversation first.",
            400
        )

    text = text.strip()

    if len(text) < 50:
        return err(
            "too_short",
            "That is too short to compact (minimum 50 characters).",
            400
        )

    if len(text) > cfg.max_input_chars:
        return err(
            "too_long",
            "Conversation is %d characters; the limit is %d. Split it into parts."
            % (len(text), cfg.max_input_chars),
            413
        )

    mode = body.get("mode", "balanced")

    if mode not in compactor.MODES:
        return err(
            "bad_request",
            "Unknown mode.",
            400
        )

    model = body.get("model") or cfg.model

    if not isinstance(model, str) or not MODEL_RE.match(model):
        return err(
            "bad_request",
            "Invalid model name.",
            400
        )

    try:
        installed = provider_models(cfg)

    except (OllamaError, groq_client.GroqError) as e:
        return err(
            e.code,
            e.message,
            e.status
        )

    if model not in installed:
        if cfg.provider == "ollama":
            message = (
                "Model '%s' is not installed. Run: ollama pull %s"
                % (model, model)
            )
        else:
            message = (
                "Groq model '%s' is unavailable. "
                "Choose a model listed by Groq."
                % model
            )

        return err(
            "model_missing",
            message,
            404
        )

    slots = _get_slots()

    if not slots.acquire(blocking=False):
        return err(
            "busy",
            "Another compaction is running. Wait for it to finish.",
            429
        )

    if cfg.provider == "groq":
        stream_fn = lambda m, messages, options: groq_client.chat_stream(
            "",
            m,
            messages,
            options,
            cfg.connect_timeout,
            cfg.read_timeout,
            cfg.groq_api_key
        )

    else:
        stream_fn = lambda m, messages, options: ollama_client.chat_stream(
            cfg.ollama_base,
            m,
            messages,
            options,
            cfg.connect_timeout,
            cfg.read_timeout,
            cfg.api_key
        )

    def gen():
        try:
            for ev in compactor.compact(
                text,
                mode,
                model,
                cfg,
                stream_fn
            ):
                yield json.dumps(
                    ev,
                    ensure_ascii=False
                ) + "\n"

        except (OllamaError, groq_client.GroqError) as e:
            yield json.dumps({
                "type": "error",
                "error": {
                    "code": e.code,
                    "message": e.message
                }
            }) + "\n"

        except Exception as exc:
            app.logger.error(
                "compaction failed: %s",
                type(exc).__name__
            )

            yield json.dumps({
                "type": "error",
                "error": {
                    "code": "server_error",
                    "message": "Unexpected server error."
                }
            }) + "\n"

        finally:
            slots.release()

    resp = Response(
        stream_with_context(gen()),
        mimetype="application/x-ndjson"
    )

    resp.headers["X-Accel-Buffering"] = "no"

    return resp


@app.get("/api/memories")
def get_astro_memories():
    return jsonify({
        "ok": True,
        "memories": memory_store.get_memories()
    })


@app.post("/api/memories")
def save_astro_memory():
    body = request.get_json(silent=True) or {}
    content = body.get("content")

    if not isinstance(content, str) or not content.strip():
        return err(
            "bad_request",
            "Memory content is required.",
            400
        )

    if len(content) > 2000:
        return err(
            "too_large",
            "Memory is too long.",
            413
        )

    memory_store.save_memory(content)

    return jsonify({
        "ok": True,
        "message": "Memory saved."
    })


@app.delete("/api/memories")
def clear_astro_memories():
    memory_store.clear_memories()

    return jsonify({
        "ok": True,
        "message": "Memories cleared."
    })


@app.delete("/api/memories/<int:memory_id>")
def delete_astro_memory(memory_id):
    deleted = memory_store.delete_memory(memory_id)

    if not deleted:
        return err(
            "not_found",
            "Memory not found.",
            404
        )

    return jsonify({
        "ok": True,
        "message": "Memory deleted."
    })


@app.post("/api/chat")
def astro_chat_route():
    cfg = config.get()

    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return err(
            "bad_request",
            "Invalid JSON.",
            400
        )

    raw_messages = body.get("messages")

    if not isinstance(raw_messages, list):
        return err(
            "bad_request",
            "Messages must be a list.",
            400
        )

    messages = []

    for item in raw_messages[-16:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if content and len(content) <= 8000:
            messages.append({
                "role": role,
                "content": content
            })

    if not messages or messages[-1]["role"] != "user":
        return err(
            "bad_request",
            "Enter a message first.",
            400
        )

    if sum(len(m["content"]) for m in messages) > 30000:
        return err(
            "too_large",
            "Conversation is too long.",
            413
        )

    system_prompt = (
        "You are ASTRO 6, a helpful personal AI assistant. "
        "Speak naturally in Tamil, Tanglish, or English based on the user's language. "
        "Help with coding, civil engineering, technical questions, writing, "
        "learning, and general tasks. Give accurate, practical answers. "
        "Never invent facts, claim actions you did not perform, "
        "or pretend to have web access when unavailable. "
        "Explain uncertainty honestly."
    )

    saved_memories = memory_store.get_memories()

    if saved_memories:
        memory_text = "\n".join(
            "- " + item["content"]
            for item in saved_memories
        )

        system_prompt += (
            "\n\nImportant facts remembered about the user:\n"
            + memory_text
            + "\nUse these facts when relevant."
        )

    chat_messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ] + messages

    slots = _get_slots()

    if not slots.acquire(blocking=False):
        return err(
            "busy",
            "Another AI request is running.",
            429
        )

    options = {
        "temperature": 0.4,
        "num_predict": 700
    }

    if cfg.provider == "groq":
        stream_fn = lambda: groq_client.chat_stream(
            "",
            cfg.model,
            chat_messages,
            options,
            cfg.connect_timeout,
            cfg.read_timeout,
            cfg.groq_api_key
        )

    else:
        stream_fn = lambda: ollama_client.chat_stream(
            cfg.ollama_base,
            cfg.model,
            chat_messages,
            options,
            cfg.connect_timeout,
            cfg.read_timeout,
            cfg.api_key
        )

    def generate():
        try:
            for piece in stream_fn():
                if piece:
                    yield json.dumps({
                        "type": "delta",
                        "text": piece
                    }, ensure_ascii=False) + "\n"

            yield json.dumps({
                "type": "done"
            }) + "\n"

        except (OllamaError, groq_client.GroqError) as exc:
            yield json.dumps({
                "type": "error",
                "error": {
                    "code": exc.code,
                    "message": exc.message
                }
            }, ensure_ascii=False) + "\n"

        except Exception as exc:
            app.logger.error(
                "ASTRO chat failed: %s",
                type(exc).__name__
            )

            yield json.dumps({
                "type": "error",
                "error": {
                    "code": "server_error",
                    "message": "ASTRO could not complete the response."
                }
            }) + "\n"

        finally:
            slots.release()

    response = Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson"
    )

    response.headers["X-Accel-Buffering"] = "no"

    return response


@app.get("/")
def index():
    return send_from_directory(
        STATIC_DIR,
        "index.html"
    )


@app.get("/<path:path>")
def static_files(path):
    if path.startswith("api/"):
        return err(
            "not_found",
            "Unknown API route.",
            404
        )

    return send_from_directory(
        STATIC_DIR,
        path
    )


@app.errorhandler(404)
def not_found(_e):
    return err(
        "not_found",
        "Not found.",
        404
    )


@app.errorhandler(500)
def server_error(_e):
    return err(
        "server_error",
        "Unexpected server error.",
        500
    )


def main():
    cfg = config.get()

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    print(
        "COMPACTION v%s on http://%s:%d"
        % (VERSION, cfg.host, cfg.port)
    )

    print(
        "Provider: %s   model: %s   token required: %s"
        % (cfg.provider, cfg.model, bool(cfg.token))
    )

    app.run(
        host=cfg.host,
        port=cfg.port,
        threaded=True
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))