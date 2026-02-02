from __future__ import annotations

import hashlib

from ..config import Settings
from ..llm.client import GeminiClient, LlmError
from ..llm.prompts import build_thread_extraction_prompt
from ..llm.schemas import ThreadExtraction
from ..store.models import CanonicalEvent, SignalRecord
from .verify import enforce_citations


def extract_signals_for_thread(*, settings: Settings, events: list[CanonicalEvent]) -> list[SignalRecord]:
    if not events:
        return []
    client = GeminiClient(settings)
    prompt = build_thread_extraction_prompt(events=events, body_mode=settings.llm_body_mode)
    result = client.generate_json(prompt)
    extraction = ThreadExtraction.model_validate(result.data)
    allowed = {e.event_id for e in events}
    extraction = enforce_citations(extraction, allowed_event_ids=allowed)

    conversation_id = events[0].conversation_id or "unknown"
    out: list[SignalRecord] = []
    for s in extraction.signals:
        # stable-enough ID: conversation + summary + evidence set
        base = f"{conversation_id}|{s.kind}|{s.summary}|{'|'.join(sorted(s.evidence_event_ids))}"
        signal_id = "sig:" + hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()[:24]
        out.append(
            SignalRecord(
                signal_id=signal_id,
                conversation_id=conversation_id,
                kind=s.kind,
                summary=s.summary,
                due_date=s.due_date,
                evidence_event_ids=s.evidence_event_ids,
            )
        )
    return out


def safe_extract_signals_for_thread(*, settings: Settings, events: list[CanonicalEvent]) -> list[SignalRecord]:
    try:
        return extract_signals_for_thread(settings=settings, events=events)
    except LlmError:
        return []

