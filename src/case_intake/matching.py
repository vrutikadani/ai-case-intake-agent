"""Identity resolution: which case, if any, this email belongs to.

Order of preference, most exact first:

1. Full key: normalized customer ID + order ID. Matches an existing case or
   defines a new one. This is the only path that can CREATE.
2. Thread memory: a reply in a thread already mapped to a case, if the mapping
   is still trusted (see thread_memory.py).
3. Order only: exactly one open case has this order number.
4. Anything else is REVIEW. Missing identifiers are never filled in or guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .models import Decision, Email
from .normalization import case_key
from .thread_memory import ThreadMemory
from .tracker import OPEN_STATUSES, CaseTracker


@dataclass
class Resolution:
    decision: Decision
    method: str                     # case_key | new_case_key | thread_memory | order_only | none
    case_key: Optional[str]
    reason: str
    candidates: list[str] = field(default_factory=list)


def resolve(customer_id: Optional[str], order_id: Optional[str], email: Email,
            tracker: CaseTracker, threads: ThreadMemory, settings: Settings) -> Resolution:
    entry, thread_reason = threads.lookup(email.thread_id, email.received_at,
                                          settings.thread_memory_ttl_days, order_id)

    # 1. full key
    if customer_id and order_id:
        key = case_key(customer_id, order_id)
        existing = tracker.get(key)
        if existing is None:
            return Resolution(Decision.CREATE_CASE, "new_case_key", key, f"no case with key {key}")
        if existing.status not in OPEN_STATUSES:
            return Resolution(Decision.REVIEW, "case_key", key,
                              f"case {key} is {existing.status}; reopening is a human decision", [key])
        return Resolution(Decision.UPDATE_CASE, "case_key", key, f"exact key match {key}")

    # 2. thread memory
    if entry is not None:
        case = tracker.get(entry.case_key)
        same_customer = customer_id is None or entry.case_key.startswith(f"{customer_id}|")
        if case is not None and case.status in OPEN_STATUSES and same_customer:
            return Resolution(Decision.UPDATE_CASE, "thread_memory", entry.case_key, thread_reason)
        if case is None or case.status not in OPEN_STATUSES:
            thread_reason = f"thread mapped to {entry.case_key}, which is no longer open"
        else:
            thread_reason = f"thread mapped to {entry.case_key} but this message names customer {customer_id}"

    # 3. order only
    if order_id:
        matches = [c for c in tracker.by_order(order_id) if c.status in OPEN_STATUSES]
        if customer_id:
            matches = [c for c in matches if c.customer_id == customer_id]
        if len(matches) == 1:
            return Resolution(Decision.UPDATE_CASE, "order_only", matches[0].case_key,
                              f"exactly one open case has order {order_id}")
        if len(matches) > 1:
            keys = [c.case_key for c in matches]
            return Resolution(Decision.REVIEW, "order_only", None,
                              f"{len(matches)} open cases share order {order_id}", keys)
        return Resolution(Decision.REVIEW, "none", None,
                          f"order {order_id} has no open case and no customer ID was found, "
                          f"so a new case cannot be keyed ({thread_reason})")

    # 4. nothing safe to act on
    missing = "order or invoice ID" if customer_id else "customer and order IDs"
    return Resolution(Decision.REVIEW, "none", None, f"no {missing}; {thread_reason}")
