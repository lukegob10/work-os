from __future__ import annotations

import hashlib

from ..store.db import utc_now_iso
from ..store.models import OpenLoopRecord, SignalRecord


OPEN_LOOP_KINDS = {"question", "action", "decision_needed", "followup"}


def signals_to_open_loops(signals: list[SignalRecord], *, owner: str = "me") -> list[OpenLoopRecord]:
    now = utc_now_iso()
    out: list[OpenLoopRecord] = []
    for s in signals:
        if s.kind not in OPEN_LOOP_KINDS:
            continue
        base = f"{s.conversation_id}|{s.kind}|{s.summary}|{'|'.join(sorted(s.evidence_event_ids))}"
        loop_id = "loop:" + hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()[:24]
        out.append(
            OpenLoopRecord(
                loop_id=loop_id,
                conversation_id=s.conversation_id,
                kind=s.kind,
                status="open",
                summary=s.summary,
                owner=owner,
                due_date=s.due_date,
                created_at=now,
                last_touched_at=now,
                evidence_event_ids=s.evidence_event_ids,
            )
        )
    return out

