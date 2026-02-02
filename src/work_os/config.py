from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


LlmBodyMode = Literal["full", "snippet", "redacted"]
EmailIngestMode = Literal["local_json", "outlook", "both"]


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
    email_ingest_mode: EmailIngestMode
    outlook_account: str | None
    gemini_api_key: str | None
    llm_model: str
    llm_temperature: float
    llm_body_mode: LlmBodyMode
    filter_email_subject_deny: list[str]
    filter_email_participant_deny: list[str]
    filter_email_subject_allow: list[str]
    filter_email_participant_allow: list[str]


def load_settings() -> Settings:
    _maybe_load_dotenv()
    llm_body_mode = _env("WORK_OS_LLM_BODY_MODE", "snippet") or "snippet"
    if llm_body_mode not in ("full", "snippet", "redacted"):
        llm_body_mode = "snippet"
    default_email_mode = "outlook" if sys.platform == "win32" else "local_json"
    email_ingest_mode = _env("WORK_OS_EMAIL_INGEST_MODE", default_email_mode) or default_email_mode
    if email_ingest_mode not in ("local_json", "outlook", "both"):
        email_ingest_mode = default_email_mode
    return Settings(
        db_path=_env_path("WORK_OS_DB_PATH", "data/work_os.db"),
        uploads_dir=_env_path("WORK_OS_UPLOADS_DIR", "data/uploads"),
        local_emails_dir=_env_path("WORK_OS_LOCAL_EMAILS_DIR", "data/local_emails"),
        briefs_dir=_env_path("WORK_OS_BRIEFS_DIR", "data/briefs"),
        email_ingest_mode=email_ingest_mode,  # type: ignore[assignment]
        outlook_account=_env("WORK_OS_OUTLOOK_ACCOUNT"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        llm_model=_env("WORK_OS_LLM_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
        llm_temperature=_env_float("WORK_OS_LLM_TEMPERATURE", 0.2),
        llm_body_mode=llm_body_mode,  # type: ignore[assignment]
        filter_email_subject_deny=_env_list("WORK_OS_FILTER_EMAIL_SUBJECT_DENY"),
        filter_email_participant_deny=_env_list("WORK_OS_FILTER_EMAIL_PARTICIPANT_DENY"),
        filter_email_subject_allow=_env_list("WORK_OS_FILTER_EMAIL_SUBJECT_ALLOW"),
        filter_email_participant_allow=_env_list("WORK_OS_FILTER_EMAIL_PARTICIPANT_ALLOW"),
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


def _env_list(name: str, default: str = "") -> list[str]:
    raw = _env(name, default) or ""
    parts = [p.strip() for p in re.split(r"[;\n]+", raw) if p.strip()]
    return parts
