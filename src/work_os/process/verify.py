from __future__ import annotations

from ..llm.schemas import ThreadExtraction


def enforce_citations(extraction: ThreadExtraction, *, allowed_event_ids: set[str]) -> ThreadExtraction:
    verified = []
    for signal in extraction.signals:
        if not signal.evidence_event_ids:
            continue
        if any(eid not in allowed_event_ids for eid in signal.evidence_event_ids):
            continue
        verified.append(signal)
    return ThreadExtraction(thread_summary=extraction.thread_summary, signals=verified)

