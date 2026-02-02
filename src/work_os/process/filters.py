from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import Settings
from ..store.models import CanonicalEvent


DEFAULT_SUBJECT_DENY = [
    r"^\s*automatic reply\b",
    r"\bout of office\b",
    r"\bundeliverable\b",
    r"\bdelivery status notification\b",
    r"\bnewsletter\b",
    r"\bdaily digest\b",
    r"\bnotification\b",
    r"\bdo not reply\b",
]

DEFAULT_PARTICIPANT_DENY = [
    r"\bno[- ]?reply\b",
    r"\bdo[- ]?not[- ]?reply\b",
    r"\bmailer-daemon\b",
    r"\bpostmaster\b",
]


@dataclass(frozen=True)
class EmailFilterConfig:
    subject_deny: list[re.Pattern[str]]
    participant_deny: list[re.Pattern[str]]
    subject_allow: list[re.Pattern[str]]
    participant_allow: list[re.Pattern[str]]


def build_email_filter_config(settings: Settings) -> EmailFilterConfig:
    return EmailFilterConfig(
        subject_deny=_compile(DEFAULT_SUBJECT_DENY + settings.filter_email_subject_deny),
        participant_deny=_compile(DEFAULT_PARTICIPANT_DENY + settings.filter_email_participant_deny),
        subject_allow=_compile(settings.filter_email_subject_allow),
        participant_allow=_compile(settings.filter_email_participant_allow),
    )


def filter_events_for_processing(events: list[CanonicalEvent], *, settings: Settings) -> list[CanonicalEvent]:
    cfg = build_email_filter_config(settings)
    out: list[CanonicalEvent] = []
    for e in events:
        if _is_noise(e, cfg):
            continue
        out.append(e)
    return out


def _is_noise(e: CanonicalEvent, cfg: EmailFilterConfig) -> bool:
    if not e.source.startswith("email_"):
        return False
    subject = e.title or ""
    participants = " ; ".join(e.participants or [])

    if _matches_any(subject, cfg.subject_allow) or _matches_any(participants, cfg.participant_allow):
        return False
    if _matches_any(subject, cfg.subject_deny):
        return True
    if _matches_any(participants, cfg.participant_deny):
        return True
    return False


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    for p in patterns:
        if p.search(text):
            return True
    return False


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for raw in patterns:
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(re.compile(raw, re.IGNORECASE))
        except re.error:
            continue
    return out
