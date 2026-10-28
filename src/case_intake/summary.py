"""Daily operational summary.

One message a day instead of one alert per review item. Early versions sent a
notification for every email that needed review; on a busy day that is the
alert fatigue the system was meant to remove.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .models import AuditRecord


def daily_summary(records: Iterable[AuditRecord]) -> dict:
    recs = list(records)
    counts = Counter(r.decision for r in recs)
    created = [r for r in recs if r.decision == "CREATE_CASE"]
    updated = [r for r in recs if r.decision == "UPDATE_CASE"]
    review = [r for r in recs if r.decision == "REVIEW"]
    held = [r for r in recs if r.decision == "HOLD"]
    prefiltered = sum(1 for r in recs if r.prefilter_rule)
    return {
        "events": len(recs),
        "dry_run": any(r.dry_run for r in recs),
        "decisions": {k: counts.get(k, 0) for k in ("CREATE_CASE", "UPDATE_CASE", "REVIEW", "IGNORE", "HOLD")},
        "model_calls": sum(1 for r in recs if r.model_called),
        "ignored_before_model": prefiltered,
        "new_cases": [{"case_key": r.case_key, "owner": r.owner, "event_id": r.event_id} for r in created],
        "updated_cases": [{"case_key": r.case_key, "method": r.match_method, "event_id": r.event_id} for r in updated],
        "review_queue": [{"event_id": r.event_id, "reason": r.review_reason} for r in review],
        "failures": [{"event_id": r.event_id, "reason": r.reason} for r in held],
        "unassigned": [r.case_key for r in created if r.owner == "ar-shared-queue"],
    }


def render_text(summary: dict) -> str:
    d = summary["decisions"]
    lines = [
        f"Case intake summary: {summary['events']} emails"
        + (" (DRY RUN: nothing was written)" if summary["dry_run"] else ""),
        f"  new cases {d['CREATE_CASE']} | updated {d['UPDATE_CASE']} | review {d['REVIEW']} | "
        f"ignored {d['IGNORE']} | held for retry {d['HOLD']}",
        f"  model calls {summary['model_calls']} ({summary['ignored_before_model']} emails discarded before the model)",
    ]
    if summary["review_queue"]:
        lines.append("  Needs review:")
        lines += [f"    - {r['event_id']}: {r['reason']}" for r in summary["review_queue"]]
    if summary["failures"]:
        lines.append("  Held for retry:")
        lines += [f"    - {r['event_id']}: {r['reason']}" for r in summary["failures"]]
    if summary["unassigned"]:
        lines.append(f"  New cases with no routing rule (shared queue): {', '.join(summary['unassigned'])}")
    return "\n".join(lines)
