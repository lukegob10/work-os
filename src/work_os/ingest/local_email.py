from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..store.models import CanonicalEvent, stable_email_event_id, sha256_text


@dataclass(frozen=True)
class LocalEmail:
    source: str
    message_id: str
    conversation_id: str | None
    timestamp: str
    participants: list[str]
    subject: str
    body: str


def ingest_local_emails(*, emails_dir: Path) -> list[CanonicalEvent]:
    emails_dir.mkdir(parents=True, exist_ok=True)
    events: list[CanonicalEvent] = []
    for path in sorted(emails_dir.glob("*.json")):
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        email = _parse_local_email(data, fallback_message_id=path.stem)
        if email.source not in ("email_inbox", "email_sent", "email_folder"):
            continue
        event_id = stable_email_event_id(email.source, email.message_id)
        events.append(
            CanonicalEvent(
                event_id=event_id,
                source=email.source,  # type: ignore[arg-type]
                source_account=None,
                conversation_id=email.conversation_id,
                timestamp=email.timestamp,
                participants=email.participants,
                title=email.subject,
                body_text=email.body,
                extracted_text=None,
                attachments_or_links=[],
                raw_pointer=str(path),
            )
        )
    return events


def _parse_local_email(data: dict[str, Any], *, fallback_message_id: str) -> LocalEmail:
    source = str(data.get("source") or "email_inbox")
    message_id = str(data.get("message_id") or data.get("id") or fallback_message_id)
    conversation_id = data.get("conversation_id")
    timestamp_raw = data.get("timestamp") or data.get("received_at") or data.get("sent_at")
    timestamp = _normalize_timestamp(timestamp_raw)
    participants = _participants(data)
    subject = str(data.get("subject") or data.get("title") or "(no subject)")
    body = str(data.get("body") or data.get("body_text") or "")
    if not message_id:
        message_id = sha256_text(subject + body)[:24]
    return LocalEmail(
        source=source,
        message_id=message_id,
        conversation_id=str(conversation_id) if conversation_id else None,
        timestamp=str(timestamp),
        participants=participants,
        subject=subject,
        body=body,
    )


def _normalize_timestamp(value: object) -> str:
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        # Accept Zulu timestamps.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _participants(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("from", "to", "cc", "participants"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend([str(v) for v in value if v])
        elif isinstance(value, dict):
            for v in value.values():
                if v:
                    out.append(str(v))
    # normalize + dedupe
    seen: set[str] = set()
    clean: list[str] = []
    for v in out:
        v = v.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        clean.append(v)
    return clean
