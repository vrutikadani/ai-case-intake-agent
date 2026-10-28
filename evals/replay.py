"""Synthetic replay validation.

    python evals/replay.py           # print the report and write evals/report.json
    python evals/replay.py --check   # fail if the committed report is stale

These are not production metrics. Every email, case and model output is
invented, and some model outputs are wrong on purpose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from case_intake.replay import load_fixtures, run, score  # noqa: E402
from case_intake.summary import daily_summary, render_text  # noqa: E402


def build() -> dict:
    emails, outputs, world, labels = load_fixtures()
    initial = {c["case_key"] for c in world["cases"]}
    ctx, results = run(True, emails, outputs, world)
    report = score(results, labels, ctx, initial)
    report["daily_summary"] = daily_summary(ctx.audit.records())
    _, dry_results = run(False, emails, outputs, world)
    report["dry_run_writes"] = sum(1 for r in dry_results if r.audit.wrote)
    return report


def main() -> int:
    report = build()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    out = ROOT / "evals" / "report.json"
    if "--check" in sys.argv:
        if not out.exists() or out.read_text() != text:
            print("evals/report.json is stale; run python evals/replay.py")
            return 1
        print("report up to date")
        return 0
    out.write_text(text)
    print("SYNTHETIC REPLAY VALIDATION (not production metrics)\n")
    for k, v in report.items():
        if k not in ("daily_summary", "mismatches"):
            print(f"  {k}: {v}")
    print("\n  expected vs actual decision differences:")
    for m in report["mismatches"]:
        print(f"    {m['event_id']} [{m['scenario']}]: expected {m['expected']}, got {m['got']}")
    print("\n" + render_text(report["daily_summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
