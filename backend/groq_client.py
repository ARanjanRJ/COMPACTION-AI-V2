"""Groq client using Groq's OpenAI-compatible API."""
import json
from typing import Dict, Iterator, List
import requests


class GroqError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}


def list_models(api_key: str, connect_timeout: float, read_timeout: float = 10.0) -> List[str]:
    if not api_key:
        raise GroqError("groq_auth", "GROQ_API_KEY is not configured.", 401)
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers=_headers(api_key),
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout:
        raise GroqError("groq_timeout", "Groq did not answer in time.", 504)
    except requests.RequestException:
        raise GroqError("groq_unavailable", "Cannot reach Groq. Check your internet connection.", 503)
    if r.status_code in (401, 403):
        raise GroqError("groq_auth", "Groq rejected the API key. Check GROQ_API_KEY.", 401)
    if r.status_code != 200:
        raise GroqError("groq_error", "Groq returned HTTP %d while listing models." % r.status_code, 502)
    try:
        data = r.json()
        return sorted(str(item["id"]) for item in data.get("data", []) if isinstance(item, dict) and item.get("id"))
    except (ValueError, AttributeError, KeyError, TypeError):
        raise GroqError("bad_response", "Groq sent an unreadable model list.", 502)


def model_available(model: str, installed: List[str]) -> bool:
    return model in installed


def chat_stream(
    base: str,
    model: str,
    messages: List[Dict[str, str]],
    options: Dict,
    connect_timeout: float,
    read_timeout: float,
    api_key: str = "",
) -> Iterator[str]:
    """Yield content deltas from Groq's server-sent event stream."""
    if not api_key:
        raise GroqError("groq_auth", "GROQ_API_KEY is not configured.", 401)
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": options.get("temperature", 0.0),
        "max_tokens": options.get("num_predict", 1000),
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=_headers(api_key),
            stream=True,
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout:
        raise GroqError("groq_timeout", "Groq took too long to start answering.", 504)
    except requests.RequestException:
        raise GroqError("groq_unavailable", "Cannot reach Groq. Check your internet connection.", 503)
    try:
        if resp.status_code in (401, 403):
            raise GroqError("groq_auth", "Groq rejected the API key. Check GROQ_API_KEY.", 401)
        if resp.status_code == 404:
            raise GroqError("model_missing", "Groq model '%s' is unavailable. Choose a model listed by Groq." % model, 404)
        if resp.status_code == 429:
            raise GroqError("rate_limited", "Groq rate limit reached. Wait and try again.", 429)
        if resp.status_code != 200:
            raise GroqError("groq_error", "Groq returned HTTP %d." % resp.status_code, 502)
        resp.encoding = "utf-8"
        got_done = False
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if not raw.startswith("data:"):
                    continue
                data_text = raw[5:].strip()
                if data_text == "[DONE]":
                    got_done = True
                    break
                try:
                    data = json.loads(data_text)
                except ValueError:
                    raise GroqError("bad_response", "Groq sent a response that could not be read.", 502)
                choices = data.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        yield piece
                    if choices[0].get("finish_reason"):
                        got_done = True
        except requests.Timeout:
            raise GroqError("groq_timeout", "Groq stopped responding while generating.", 504)
        except requests.RequestException:
            raise GroqError("groq_unavailable", "Lost the connection to Groq while generating.", 503)
        if not got_done:
            raise GroqError("bad_response", "Groq ended the response early.", 502)
    finally:
        resp.close()
