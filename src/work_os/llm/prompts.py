from __future__ import annotations

import json
from collections.abc import Iterable

from ..config import LlmBodyMode, redact_text
from ..store.models import CanonicalEvent


def build_thread_extraction_prompt(*, events: list[CanonicalEvent], body_mode: LlmBodyMode) -> str:
    event_payload = [_event_for_llm(e, body_mode=body_mode) for e in events]
    schema_hint = {
        "thread_summary": "optional string",
        "signals": [
            {
                "kind": "question|action|decision_needed|followup|risk",
                "summary": "string",
                "due_date": "YYYY-MM-DD or null",
                "evidence_event_ids": ["event_id", "..."],
            }
        ],
    }
    return "\n".join(
        [
            "You are a strict information extraction engine.",
            "Return JSON only. Do not wrap in markdown. Do not include commentary.",
            "Rules:",
            "- Only use evidence from the provided events.",
            "- Every signal MUST include evidence_event_ids referencing provided event_id values.",
            "- If you are unsure, omit the signal (do not guess).",
            "",
            f"Output schema (shape, not exact types): {json.dumps(schema_hint)}",
            "",
            f"Events: {json.dumps(event_payload)}",
        ]
    )


def build_react_planner_prompt(*, question: str, tools: dict[str, str], context: str) -> str:
    return "\n".join(
        [
            "You are a bounded ReAct planner for an email+files workspace.",
            "Decide the next action to take and return JSON only.",
            "You may only call one of the allowed actions.",
            "Stop when you can answer with evidence.",
            "",
            "Allowed actions:",
            json.dumps(tools, indent=2),
            "",
            "Return JSON with shape:",
            json.dumps(
                {
                    "action": "search_events|get_event|list_open_loops|final",
                    "args": {"...": "tool args"},
                    "scratchpad": "short reasoning notes (optional)",
                }
            ),
            "",
            f"Question: {question}",
            "",
            f"Context so far:\n{context}",
        ]
    )


def build_react_final_prompt(*, question: str, gathered_context: str) -> str:
    return "\n".join(
        [
            "You are a precise analyst. Answer the question using ONLY the provided context.",
            "If you cannot answer, say what is missing.",
            "Include evidence by listing event_id values you relied on.",
            "Return plain text (not JSON).",
            "",
            f"Question: {question}",
            "",
            f"Context:\n{gathered_context}",
        ]
    )


def _event_for_llm(e: CanonicalEvent, *, body_mode: LlmBodyMode) -> dict[str, object]:
    text = e.body_text or e.extracted_text or ""
    if body_mode == "snippet":
        text = text[:2000]
    elif body_mode == "redacted":
        text = redact_text(text)[:2000]
    return {
        "event_id": e.event_id,
        "source": e.source,
        "timestamp": e.timestamp,
        "title": e.title,
        "participants": e.participants,
        "text": text,
    }

