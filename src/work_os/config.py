from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


LlmBodyMode = Literal["full", "snippet", "redacted"]


_PHONE_RE = re.compile(r"(?<!\\d)(?:\\+?1[\\s.-]?)?(?:\\(\\d{3}\\)|\\d{3})[\\s.-]?\\d{3}[\\s.-]?\\d{4}(?!\\d)")
_EMAIL_RE = re.compile(r"\\b[\\w.+'-]+@[\\w.-]+\\.[A-Za-z]{2,}\\b")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _env_path(name: str, default: str) -> Path:
    return Path(_env(name, default) or default)


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    db_path: Path
    uploads_dir: Path
    local_emails_dir: Path
    briefs_dir: Path
    gemini_api_key: str | None
    llm_model: str
    llm_temperature: float
    llm_body_mode: LlmBodyMode


def load_settings() -> Settings:
    _maybe_load_dotenv()
    llm_body_mode = _env("WORK_OS_LLM_BODY_MODE", "snippet") or "snippet"
    if llm_body_mode not in ("full", "snippet", "redacted"):
        llm_body_mode = "snippet"
    return Settings(
        db_path=_env_path("WORK_OS_DB_PATH", "data/work_os.db"),
        uploads_dir=_env_path("WORK_OS_UPLOADS_DIR", "data/uploads"),
        local_emails_dir=_env_path("WORK_OS_LOCAL_EMAILS_DIR", "data/local_emails"),
        briefs_dir=_env_path("WORK_OS_BRIEFS_DIR", "data/briefs"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        llm_model=_env("WORK_OS_LLM_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
        llm_temperature=_env_float("WORK_OS_LLM_TEMPERATURE", 0.2),
        llm_body_mode=llm_body_mode,  # type: ignore[assignment]
    )


def redact_text(text: str) -> str:
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    return text


def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv(override=False)

