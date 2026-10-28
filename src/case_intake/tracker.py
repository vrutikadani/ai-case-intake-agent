"""The case tracker: the only place case state lives.

In the original design this was a SharePoint list; here it is an in-memory
store with the same contract. Two rules matter more than the storage:

- Updates append to history. Status, owner and the original description are
  never overwritten by an email.
- The schema is checked once, when the tracker is opened, and cached. A
  missing column stops the run before any email is processed, instead of
  failing halfway through a batch.
"""
from __future__ import annotations

import copy
from typing import Optional

from .models import Case, CaseUpdate

REQUIRED_FIELDS = ("case_key", "customer_id", "order_id", "customer_name", "case_type",
                   "owner", "status", "created_at", "updated_at", "history")
OPEN_STATUSES = ("open", "in_progress", "waiting_on_customer")


class TrackerSchemaError(Exception):
    pass


class TrackerWriteError(Exception):
    pass


class CaseTracker:
    def __init__(self, cases: Optional[list[dict]] = None, schema: tuple[str, ...] = REQUIRED_FIELDS):
        missing = [f for f in REQUIRED_FIELDS if f not in schema]
        if missing:
            raise TrackerSchemaError(f"tracker is missing fields: {', '.join(missing)}")
        self.schema = schema                  # discovered once, reused for every event
        self._cases: dict[str, Case] = {}
        self.fail_next_write = False          # test hook for downstream write failures
        for c in cases or []:
            c = dict(c)
            c["history"] = [CaseUpdate(**h) for h in c.get("history", [])]
            case = Case(**c)
            self._cases[case.case_key] = case

    # reads ------------------------------------------------------------------
    def get(self, key: str) -> Optional[Case]:
        return self._cases.get(key)

    def by_order(self, order_id: str) -> list[Case]:
        return [c for c in self._cases.values() if c.order_id == order_id]

    def all(self) -> list[Case]:
        return sorted(self._cases.values(), key=lambda c: c.case_key)

    def snapshot(self) -> list[dict]:
        return [c.to_dict() for c in self.all()]

    # writes -----------------------------------------------------------------
    def _check_write(self) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise TrackerWriteError("tracker rejected the write")

    def create(self, case: Case) -> Case:
        self._check_write()
        if case.case_key in self._cases:
            raise TrackerWriteError(f"case {case.case_key} already exists")
        self._cases[case.case_key] = case
        return case

    def append_update(self, key: str, update: CaseUpdate) -> Case:
        self._check_write()
        case = self._cases[key]
        if any(h.event_id == update.event_id for h in case.history):
            return case                       # same event twice: no second entry
        case.history.append(update)
        case.updated_at = update.at
        return case

    def clone(self) -> "CaseTracker":
        return copy.deepcopy(self)
