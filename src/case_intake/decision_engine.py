"""One event in, one decision out.

``process_event`` handles exactly one email per call. The original workflow
started as a batch loop over the inbox; references between iterations broke
in ways that were hard to see. One event per execution means a failure
affects one email, retries are per email, and every run produces exactly one
audit record.

Stages, in order (each one can end the run):

    idempotency -> pre-filter -> classification -> normalization -> matching -> decision -> write
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .audit_log import AuditLog
from .classifier import Classifier, ClassifierError, SchemaError, suspected_injection
from .config import Settings
from .filters import prefilter
from .matching import resolve
from .models import AuditRecord, Case, CaseUpdate, ClassifierResult, Decision, Email, PipelineResult, StageResult
from .normalization import case_key, grounded_as, normalize_customer_id, normalize_order_id
from .routing import DEFAULT_DIRECTORY, known_customer, owner_for
from .thread_memory import ThreadMemory
from .tracker import CaseTracker, TrackerWriteError


@dataclass
class Context:
    settings: Settings
    classifier: Classifier
    tracker: CaseTracker
    threads: ThreadMemory = field(default_factory=ThreadMemory)
    audit: AuditLog = field(default_factory=AuditLog)
    clock: Optional[str] = None           # fixed "now" for replays; real runs use the wall clock
    directory: dict = field(default_factory=lambda: dict(DEFAULT_DIRECTORY))   # customer master data

    def now(self) -> str:
        return self.clock or datetime.now(timezone.utc).isoformat(timespec="seconds")


def process_event(email: Email, ctx: Context) -> PipelineResult:
    """Process one email. Any unexpected error becomes an audited HOLD, never a missing record."""
    stages: list[StageResult] = []
    try:
        return _process(email, ctx, stages)
    except Exception as exc:  # noqa: BLE001 - the audit record matters more than the traceback type
        stages.append(StageResult("error", "fail", f"{type(exc).__name__}: {exc}"))
        reason = f"unexpected error ({type(exc).__name__}); nothing written, event left for retry"
        audit = AuditRecord(timestamp=ctx.now(), event_id=email.event_id, thread_id=email.thread_id,
                            decision=Decision.HOLD.value, reason=reason, prefilter_rule=None, classifier=None,
                            normalized_customer_id=None, normalized_order_id=None, case_key=None,
                            matched_case=None, match_method=None, owner=None, wrote=False,
                            dry_run=not ctx.settings.write_to_tracker, review_reason=None, model_called=False)
        ctx.audit.append(audit)
        return PipelineResult(Decision.HOLD, reason, stages, audit)


def _process(email: Email, ctx: Context, stages: list[StageResult]) -> PipelineResult:
    s = ctx.settings
    rec = dict(timestamp=ctx.now(), event_id=email.event_id, thread_id=email.thread_id,
               prefilter_rule=None, classifier=None, normalized_customer_id=None,
               normalized_order_id=None, case_key=None, matched_case=None, match_method=None,
               owner=None, wrote=False, dry_run=not s.write_to_tracker, review_reason=None,
               model_called=False)

    def finish(decision: Decision, reason: str, case_after: Optional[dict] = None) -> PipelineResult:
        if decision == Decision.REVIEW:
            rec["review_reason"] = reason
        audit = AuditRecord(decision=decision.value, reason=reason, **rec)
        ctx.audit.append(audit)
        return PipelineResult(decision, reason, stages, audit, case_after)

    # 0. idempotency: every decision except HOLD is final for an event. A
    # re-delivered email must not get a second, different answer from a
    # non-deterministic model (REVIEW once, CREATE on retry).
    prior = ctx.audit.decided(email.event_id)
    if prior is not None:
        stages.append(StageResult("idempotency", "stop", f"event already decided ({prior.decision})"))
        return finish(Decision.IGNORE, f"duplicate delivery: event already decided as {prior.decision}")
    stages.append(StageResult("idempotency", "pass", "first time this event is applied"))

    # 1. pre-filter (no model call)
    rule = prefilter(email, s)
    if rule:
        rec["prefilter_rule"] = rule
        stages.append(StageResult("pre-filter", "stop", f"discarded by rule: {rule}"))
        return finish(Decision.IGNORE, f"routine mail ({rule}); no model call")
    injection = suspected_injection(email)
    stages.append(StageResult("pre-filter", "pass",
                              "no routine rule matched" + (f"; text addresses the model: '{injection}'" if injection else ""),
                              {"suspected_injection": injection}))

    # 2. classification (the only judgment step)
    rec["model_called"] = True
    try:
        result: ClassifierResult = ctx.classifier.classify(email)
    except ClassifierError as exc:
        stages.append(StageResult("classification", "fail", f"model unavailable: {exc}"))
        return finish(Decision.HOLD, f"classifier unavailable ({exc}); event left for retry")
    except SchemaError as exc:
        stages.append(StageResult("classification", "fail", f"output rejected: {exc}"))
        return finish(Decision.REVIEW, f"classifier output failed schema validation ({exc})")
    rec["classifier"] = vars(result).copy()
    stages.append(StageResult("classification", "pass" if result.is_case else "stop",
                              f"is_case={result.is_case}, confidence={result.confidence:.2f}: {result.reason}",
                              vars(result).copy()))
    if not result.is_case:
        return finish(Decision.IGNORE, f"classifier: not a case ({result.reason})")
    if injection:
        return finish(Decision.REVIEW, f"suspected prompt injection ('{injection}'); classifier output not acted on")
    if result.confidence < s.min_confidence:
        return finish(Decision.REVIEW, f"classifier confidence {result.confidence:.2f} below {s.min_confidence}")

    # 3. normalization + grounding (code, not the model)
    cust = normalize_customer_id(result.customer_id)
    order = normalize_order_id(result.order_or_invoice_id)
    notes = []
    if result.customer_id and cust is None:
        notes.append(f"customer ID '{result.customer_id}' is malformed")
    if result.order_or_invoice_id and order is None:
        notes.append(f"order ID '{result.order_or_invoice_id}' is malformed")
    # Grounding: each ID must appear in the email next to a label of its own kind,
    # so an amount, a year, the other ID or a swapped pair can't become identity.
    ungrounded = [label for label, v in (("customer", cust), ("order", order))
                  if v and not grounded_as(label, v, email.text)]
    rec["normalized_customer_id"], rec["normalized_order_id"] = cust, order
    if ungrounded:
        stages.append(StageResult("normalization", "fail",
                                  f"model returned a {' and '.join(ungrounded)} ID that does not appear in the email "
                                  f"with a {' / '.join(ungrounded)} label", {"customer_id": cust, "order_id": order}))
        return finish(Decision.REVIEW, f"ungrounded {' and '.join(ungrounded)} ID from classifier")
    if cust and order and cust == order:
        stages.append(StageResult("normalization", "fail", "customer and order IDs are the same number"))
        return finish(Decision.REVIEW, "customer and order IDs are the same number")
    if cust and not known_customer(cust, ctx.directory):
        stages.append(StageResult("normalization", "fail", f"customer {cust} is not in the customer directory"))
        return finish(Decision.REVIEW, f"customer {cust} is not in the customer directory")
    stages.append(StageResult("normalization", "pass",
                              f"customer {result.customer_id!r} -> {cust!r}; order {result.order_or_invoice_id!r} -> {order!r}"
                              + (f" ({'; '.join(notes)})" if notes else ""),
                              {"customer_id": cust, "order_id": order,
                               "case_key": case_key(cust, order) if cust and order else None}))

    # 4. matching
    res = resolve(cust, order, email, ctx.tracker, ctx.threads, s)
    rec["case_key"] = res.case_key
    rec["match_method"] = res.method
    rec["matched_case"] = res.case_key if res.decision == Decision.UPDATE_CASE else None
    stages.append(StageResult("matching", "pass" if res.decision != Decision.REVIEW else "stop",
                              f"{res.method}: {res.reason}", {"candidates": res.candidates}))

    # 5. decision
    decision, reason = res.decision, res.reason
    if notes and decision == Decision.REVIEW:
        reason = f"{reason}; {'; '.join(notes)}"
    stages.append(StageResult("decision", "pass", f"{decision.value}: {reason}"))
    if decision not in (Decision.CREATE_CASE, Decision.UPDATE_CASE):
        return finish(decision, reason)

    # 6. write (or not, in dry-run)
    now = email.received_at
    update = CaseUpdate(at=now, event_id=email.event_id, summary=result.summary)
    if decision == Decision.CREATE_CASE:
        owner = owner_for(cust, ctx.directory)
        proposed = Case(case_key=res.case_key, customer_id=cust, order_id=order,
                        customer_name=result.customer_name, case_type=result.case_type, owner=owner,
                        status="open", created_at=now, updated_at=now, history=[update])
    else:
        existing = ctx.tracker.get(res.case_key)
        owner = existing.owner
        proposed = copy.deepcopy(existing)          # what the case would look like; tracker untouched
        if all(h.event_id != update.event_id for h in proposed.history):
            proposed.history.append(update)
            proposed.updated_at = update.at
    rec["owner"] = owner

    if not s.write_to_tracker:
        stages.append(StageResult("write", "skip", "dry run: tracker and thread memory unchanged"))
        return finish(decision, f"{reason} (dry run, nothing written)", proposed.to_dict())

    try:
        written = (ctx.tracker.create(proposed) if decision == Decision.CREATE_CASE
                   else ctx.tracker.append_update(res.case_key, update))
    except TrackerWriteError as exc:
        stages.append(StageResult("write", "fail", str(exc)))
        return finish(Decision.HOLD, f"write failed ({exc}); safe to retry, nothing was changed")
    ctx.threads.remember(email.thread_id, written.case_key, written.order_id, now)
    rec["wrote"] = True
    stages.append(StageResult("write", "pass", f"{'created' if decision == Decision.CREATE_CASE else 'updated'} {written.case_key}"))
    return finish(decision, reason, written.to_dict())
