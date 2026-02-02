from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..graphs.daily_worker import build_daily_worker
from ..graphs.qa_agent import build_qa_agent


class ReactEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._daily = build_daily_worker(settings)
        self._qa = build_qa_agent(settings)

    def run_daily(self, *, since_iso: str) -> dict[str, object]:
        return dict(self._daily.invoke({"since_iso": since_iso}))

    def answer_question(self, *, question: str, since_iso: str, max_steps: int = 6) -> dict[str, object]:
        state: dict[str, object] = {"question": question, "since_iso": since_iso, "context": "", "steps": []}
        for _ in range(max_steps):
            state = dict(self._qa.invoke(state))  # one step per invoke
            if state.get("final_answer"):
                break
        return state

