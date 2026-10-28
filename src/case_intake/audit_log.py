"""Append-only audit log: one structured record per processed event.

The log is what makes the system operable. It answers "why did this email
create a case?" and "what would have happened?" in dry-run, and it is what the
idempotency check and the daily summary read from.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from .models import AuditRecord


class AuditLog:
    def __init__(self, records: Optional[Iterable[AuditRecord]] = None):
        self._records: list[AuditRecord] = list(records or [])

    def append(self, rec: AuditRecord) -> None:
        self._records.append(rec)

    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def decided(self, event_id: str) -> Optional[AuditRecord]:
        """The final decision already made for this event in a live run, if any.
        HOLD is not final (it is meant to be retried) and dry-run records never block a live run."""
        for r in self._records:
            if r.event_id == event_id and r.decision != "HOLD" and not r.dry_run:
                return r
        return None

    def written(self, event_id: str) -> Optional[AuditRecord]:
        """The record that already changed the tracker for this event, if any."""
        for r in self._records:
            if r.event_id == event_id and r.wrote:
                return r
        return None

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(r.to_dict(), sort_keys=True) for r in self._records)
