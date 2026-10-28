"""Thread memory: follow-ups that carry no identifiers.

"Any update on this?" has no customer or order number, but its thread was
already mapped to a case when the first message was processed. Reusing that
mapping is what lets a reply update the right case instead of going to review.

It is also a way to be confidently wrong, so the mapping stops being trusted
when:

- it is older than the TTL (threads get reused for unrelated topics);
- the new message names a different order (the thread has drifted);
- the mapped case no longer exists or is closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ThreadEntry:
    case_key: str
    order_id: str
    last_seen: str


class ThreadMemory:
    def __init__(self) -> None:
        self._map: dict[str, ThreadEntry] = {}

    def get(self, thread_id: str) -> Optional[ThreadEntry]:
        return self._map.get(thread_id)

    def remember(self, thread_id: str, case_key: str, order_id: str, at: str) -> None:
        self._map[thread_id] = ThreadEntry(case_key, order_id, at)

    def lookup(self, thread_id: str, now: str, ttl_days: int,
               mentioned_order: Optional[str]) -> tuple[Optional[ThreadEntry], str]:
        """Return (entry, reason). entry is None when memory must not be used."""
        entry = self._map.get(thread_id)
        if entry is None:
            return None, "thread not seen before"
        age = (_parse(now) - _parse(entry.last_seen)).days
        if age > ttl_days:
            return None, f"thread mapping is {age} days old (limit {ttl_days})"
        if mentioned_order and mentioned_order != entry.order_id:
            return None, f"thread was mapped to order {entry.order_id} but this message names {mentioned_order}"
        return entry, f"thread mapped to {entry.case_key} {age} days ago"

    def to_dict(self) -> dict:
        return {k: vars(v) for k, v in self._map.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "ThreadMemory":
        tm = cls()
        for k, v in d.items():
            tm._map[k] = ThreadEntry(**v)
        return tm


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
