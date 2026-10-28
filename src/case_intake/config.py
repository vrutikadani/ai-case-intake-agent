"""Settings in one place. Nothing here is tuned on real traffic; every value is
a starting point a team would revisit after a dry-run period."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Trial mode. False = classify, match and log what would happen, change nothing.
    write_to_tracker: bool = field(default_factory=lambda: _env_bool("WRITE_TO_TRACKER", False))

    # Classifier output below this confidence goes to REVIEW, never to a write.
    min_confidence: float = 0.75

    # Thread memory is trusted only for this long after the last mapped message.
    thread_memory_ttl_days: int = 21

    # Pre-filter: cheap rules that run before any model call.
    routine_subject_patterns: tuple[str, ...] = (
        r"^(automatic reply|auto(-| )?reply|out of (the )?office)\b",
        r"\b(daily|weekly|monthly) ((ar|aging|ageing|statement|cash|collections?) )+report\b",
        r"^remittance advice\b",
        r"^payment (confirmation|received)\b",
        r"^(undeliverable|delivery status notification)\b",
        r"\bnewsletter\b",
    )
    non_case_senders: tuple[str, ...] = (
        "noreply@", "no-reply@", "notifications@", "mailer-daemon@", "reports@",
    )
    auto_reply_headers: tuple[str, ...] = ("auto-submitted", "x-autoreply", "x-autorespond")

