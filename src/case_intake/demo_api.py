"""JSON functions for the browser demo (run through Pyodide). The demo calls the
same pipeline the tests use; nothing is re-implemented in JavaScript."""
from __future__ import annotations

import json
from pathlib import Path

from .classifier import RecordedClassifier, RuleClassifier
from .decision_engine import process_event
from .replay import load_fixtures, new_context, run, to_email
from .summary import daily_summary, render_text

SCENARIOS = [
    ("new-case", "New blocking case", "Messy customer and order formats; nothing on file yet."),
    ("thread-reply", "Reply without identifiers", "\"Any update?\" in a thread already mapped to a case."),
    ("duplicate-format", "Duplicate formatting", "Case on file is 38262; this email says SO#038262."),
    ("routine-report", "Routine report", "An automated aging report. Discarded before any model call."),
    ("missing-order", "Missing order identifier", "A real issue, but no order or invoice number."),
    ("order-only", "Unique order-only match", "Only an invoice number, and exactly one open case has it."),
    ("ambiguous-order", "Ambiguous order match", "Two open cases share this invoice number."),
    ("dry-run", "Dry run", "A valid new case with writes turned off."),
    ("prompt-injection", "Prompt injection", "The email tells the model what to output."),
    ("hallucinated-id", "Hallucinated identifier", "The model returns an order number that is not in the email."),
]

_base = None


def _load(base: str | None = None):
    global _base
    if _base is None or base:
        _base = load_fixtures(Path(base) if base else None)
    return _base


def scenarios(base: str | None = None) -> str:
    emails, outputs, world, labels = _load(base)
    out = []
    for sid, title, blurb in SCENARIOS:
        i = next(i for i, l in enumerate(labels) if l.get("scenario") == sid)
        e = {k: v for k, v in emails[i].items() if not k.startswith("_")}
        out.append({"id": sid, "title": title, "blurb": blurb, "email": e,
                    "recorded_output": outputs[i]["output"], "expected": labels[i]["decision"],
                    "dry_run": sid == "dry-run"})
    return json.dumps(out)


def run_one(payload_json: str) -> str:
    """payload: {email, recorded_output|null, dry_run}. Fresh copy of the sample tracker each time."""
    p = json.loads(payload_json)
    _, _, world, _ = _load()
    ctx = new_context(world, write=not p.get("dry_run", False))
    email = to_email(p["email"])
    if p.get("recorded_output") is not None:
        ctx.classifier = RecordedClassifier({email.event_id: p["recorded_output"]})
    else:
        ctx.classifier = RuleClassifier()
    before = {c["case_key"]: c for c in ctx.tracker.snapshot()}
    result = process_event(email, ctx)
    out = result.to_dict()
    out["classifier_used"] = ctx.classifier.name
    out["tracker_before"] = list(before.values())
    out["tracker_after"] = ctx.tracker.snapshot()
    out["threads_after"] = ctx.threads.to_dict()
    return json.dumps(out, default=str)


def batch(dry_run: bool = False) -> str:
    emails, outputs, world, labels = _load()
    ctx, results = run(not dry_run, emails, outputs, world)
    summary = daily_summary(ctx.audit.records())
    rows = [{"event_id": r.audit.event_id, "subject": e["subject"], "decision": r.decision.value,
             "expected": l["decision"], "reason": r.reason, "model_called": r.audit.model_called,
             "wrote": r.audit.wrote, "scenario": l.get("scenario")}
            for r, e, l in zip(results, emails, labels)]
    return json.dumps({"summary": summary, "text": render_text(summary), "rows": rows,
                       "tracker_after": ctx.tracker.snapshot()}, default=str)
