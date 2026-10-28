"""Data shapes shared by every stage. Plain dataclasses, standard library only,
so the same files run in tests, in the replay harness and in the browser demo."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class Decision(str, Enum):
    IGNORE = "IGNORE"            # not a case (pre-filter or classifier)
    CREATE_CASE = "CREATE_CASE"  # new case, identity is exact
    UPDATE_CASE = "UPDATE_CASE"  # existing case, matched deterministically
    REVIEW = "REVIEW"            # a person decides: identity or judgment is not safe to automate
    HOLD = "HOLD"                # transient failure (model or tracker unavailable); retry later


@dataclass
class Email:
    event_id: str                 # unique per message; drives idempotency
    thread_id: str
    received_at: str              # ISO timestamp
    sender: str
    subject: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class ClassifierResult:
    """The only shape the rest of the pipeline accepts from the model."""
    is_case: bool
    reason: str
    case_type: Optional[str]
    customer_name: Optional[str]
    customer_id: Optional[str]
    order_or_invoice_id: Optional[str]
    summary: str
    confidence: float


@dataclass
class CaseUpdate:
    at: str
    event_id: str
    summary: str


@dataclass
class Case:
    case_key: str
    customer_id: str
    order_id: str
    customer_name: Optional[str]
    case_type: Optional[str]
    owner: str
    status: str
    created_at: str
    updated_at: str
    history: list[CaseUpdate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageResult:
    stage: str
    status: str          # pass | stop | skip | fail
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditRecord:
    timestamp: str
    event_id: str
    thread_id: str
    decision: str
    reason: str
    prefilter_rule: Optional[str]
    classifier: Optional[dict[str, Any]]
    normalized_customer_id: Optional[str]
    normalized_order_id: Optional[str]
    case_key: Optional[str]
    matched_case: Optional[str]
    match_method: Optional[str]
    owner: Optional[str]
    wrote: bool
    dry_run: bool
    review_reason: Optional[str]
    model_called: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    decision: Decision
    reason: str
    stages: list[StageResult]
    audit: AuditRecord
    case_after: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "stages": [asdict(s) for s in self.stages],
            "audit": self.audit.to_dict(),
            "case_after": self.case_after,
        }
