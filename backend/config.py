"""Configuration read from environment variables (never from the browser)."""
import os
from dataclasses import dataclass, field
from typing import List

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class Config:
    ollama_base: str
    model: str
    host: str
    port: int
    token: str
    api_key: str = ""
    provider: str = "ollama"
    groq_api_key: str = ""
    cors_origins: List[str] = field(default_factory=list)
    connect_timeout: float = 5.0
    read_timeout: float = 180.0
    max_input_chars: int = 100_000
    chunk_chars: int = 5_000
    merge_chars: int = 6_000
    num_ctx: int = 4_096
    rate_limit_per_minute: int = 60
    max_concurrent: int = 1


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def get() -> Config:
    origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    provider = os.environ.get("AI_PROVIDER", "ollama").strip().lower()
    if provider not in ("ollama", "groq"):
        provider = "ollama"
    default_model = "llama-3.3-70b-versatile" if provider == "groq" else "llama3.2:1b"
    return Config(
        ollama_base=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
        model=os.environ.get("AI_MODEL", os.environ.get("OLLAMA_MODEL", default_model)).strip(),
        host=os.environ.get("HOST", "127.0.0.1").strip(),
        port=_int("PORT", 5000),
        token=os.environ.get("COMPACTION_ACCESS_TOKEN", "").strip(),
        api_key=os.environ.get("OLLAMA_API_KEY", "").strip(),
        provider=provider,
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
        cors_origins=origins,
        connect_timeout=_float("OLLAMA_CONNECT_TIMEOUT", 5),
        read_timeout=_float("OLLAMA_READ_TIMEOUT", 180),
        max_input_chars=_int("MAX_INPUT_CHARS", 100_000),
        chunk_chars=_int("CHUNK_CHARS", 5_000),
        merge_chars=_int("MERGE_CHARS", 6_000),
        num_ctx=_int("OLLAMA_NUM_CTX", 4_096),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 60),
        max_concurrent=max(1, _int("MAX_CONCURRENT", 1)),
    )


def is_loopback(host: str) -> bool:
    return host in LOOPBACK_HOSTS


def startup_check(cfg: Config) -> None:
    if not is_loopback(cfg.host) and not cfg.token:
        raise RuntimeError(
            "Refusing to listen on %r without COMPACTION_ACCESS_TOKEN. "
            "Set a long random token in .env, or use HOST=127.0.0.1." % cfg.host
        )

    if cfg.provider == "ollama" and cfg.api_key and not cfg.ollama_base.startswith("https://"):
        raise RuntimeError(
            "OLLAMA_API_KEY is set but OLLAMA_BASE_URL is not https."
        )

    if len(cfg.token) and len(cfg.token) < 16:
        raise RuntimeError(
            "COMPACTION_ACCESS_TOKEN is too short; use at least 16 characters."
        )

    if cfg.provider == "groq" and not cfg.groq_api_key:
        raise RuntimeError(
            "AI_PROVIDER=groq but GROQ_API_KEY is missing from .env."
        )
