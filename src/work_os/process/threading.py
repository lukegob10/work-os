from __future__ import annotations

import re
from collections import defaultdict

from ..store.models import CanonicalEvent, ThreadRecord


_PREFIX_RE = re.compile(r"^(\\s*(re|fwd|fw)\\s*:\\s*)+", re.IGNORECASE)


def build_threads(events: list[CanonicalEvent]) -> list[ThreadRecord]:
    buckets: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for e in events:
        conversation_id = e.conversation_id or _fallback_conversation_id(e.title)
        buckets[conversation_id].append(e)

    threads: list[ThreadRecord] = []
    for conversation_id, bucket in buckets.items():
        bucket.sort(key=lambda ev: ev.timestamp)
        title = next((b.title for b in bucket if b.title), "(untitled)")
        last_activity = bucket[-1].timestamp
        threads.append(
            ThreadRecord(
                conversation_id=conversation_id,
                thread_title=title,
                event_ids=[b.event_id for b in bucket],
                last_activity_at=last_activity,
            )
        )
    threads.sort(key=lambda t: t.last_activity_at, reverse=True)
    return threads


def _fallback_conversation_id(subject: str) -> str:
    normalized = _PREFIX_RE.sub("", subject or "").strip().lower()
    normalized = re.sub(r"\\s+", " ", normalized)
    return f"subject:{normalized or 'unknown'}"

