import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from case_intake.classifier import RecordedClassifier  # noqa: E402
from case_intake.config import Settings  # noqa: E402
from case_intake.decision_engine import Context  # noqa: E402
from case_intake.models import Email  # noqa: E402
from case_intake.thread_memory import ThreadMemory  # noqa: E402
from case_intake.tracker import CaseTracker  # noqa: E402

NOW = "2026-10-06T12:00:00+00:00"


def existing_case(key="10442|38262", status="open", owner="collections-team-a"):
    cust, order = key.split("|")
    return dict(case_key=key, customer_id=cust, order_id=order, customer_name="Tidewater Supply Co.",
                case_type="pricing_discrepancy", owner=owner, status=status,
                created_at="2026-10-01T10:00:00+00:00", updated_at="2026-10-01T10:00:00+00:00",
                history=[dict(at="2026-10-01T10:00:00+00:00", event_id="evt-old", summary="original issue")])


def email(event_id="evt-1", subject="Invoice issue", body="We can't pay.", thread="th-1",
          sender="ap@customer.example", at=NOW, headers=None):
    return Email(event_id=event_id, thread_id=thread, received_at=at, sender=sender,
                 subject=subject, body=body, headers=headers or {})


def model(is_case=True, cust=None, order=None, conf=0.9, reason="blocking issue", case_type="billing_dispute"):
    return dict(is_case=is_case, reason=reason, case_type=case_type, customer_name=None,
                customer_id=cust, order_or_invoice_id=order, summary="summary", confidence=conf)


@pytest.fixture
def make_ctx():
    def _make(cases=None, threads=None, write=True, outputs=None):
        return Context(settings=Settings(write_to_tracker=write),
                       classifier=RecordedClassifier(outputs or {}),
                       tracker=CaseTracker(cases if cases is not None else [existing_case()]),
                       threads=ThreadMemory.from_dict(threads or {}), clock=NOW)
    return _make
