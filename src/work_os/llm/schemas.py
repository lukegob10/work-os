from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SignalKind = Literal["question", "action", "decision_needed", "followup", "risk"]


class ExtractedSignal(BaseModel):
    kind: SignalKind
    summary: str = Field(min_length=1, max_length=500)
    due_date: str | None = Field(default=None, description="ISO date (YYYY-MM-DD) if explicitly stated")
    evidence_event_ids: list[str] = Field(min_length=1)


class ThreadExtraction(BaseModel):
    thread_summary: str | None = Field(default=None, max_length=1000)
    signals: list[ExtractedSignal] = Field(default_factory=list)


class ReactAction(BaseModel):
    action: Literal["search_events", "get_event", "list_open_loops", "final"]
    args: dict[str, object] = Field(default_factory=dict)
    scratchpad: str | None = None

