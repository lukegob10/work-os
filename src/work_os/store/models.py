from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


SourceType = Literal["email_inbox", "email_sent", "email_folder", "uploaded_file"]


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_text(data: str) -> str:
    return sha256_bytes(data.encode("utf-8", errors="ignore"))


def stable_file_event_id(path: Path, content_hash: str) -> str:
    return f"file:{content_hash}"


def stable_email_event_id(source: str, message_id: str) -> str:
    return f"{source}:{message_id}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    source: SourceType
    source_account: str | None
    conversation_id: str | None
    timestamp: str
    participants: list[str]
    title: str
    body_text: str | None
    extracted_text: str | None
    attachments_or_links: list[dict[str, Any]]
    raw_pointer: str


@dataclass(frozen=True)
class ThreadRecord:
    conversation_id: str
    thread_title: str
    event_ids: list[str]
    last_activity_at: str


@dataclass(frozen=True)
class SignalRecord:
    signal_id: str
    conversation_id: str
    kind: str
    summary: str
    due_date: str | None
    evidence_event_ids: list[str]


@dataclass(frozen=True)
class OpenLoopRecord:
    loop_id: str
    conversation_id: str | None
    kind: str
    status: str
    summary: str
    owner: str
    due_date: str | None
    created_at: str
    last_touched_at: str
    evidence_event_ids: list[str]

