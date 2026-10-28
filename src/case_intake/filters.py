"""Cheap deterministic pre-filters.

They run before the model, so routine mail costs nothing to discard and can't
be misread as a case. A filter only ever discards; it never creates a case.
When in doubt a filter lets the email through, because the classifier can
still say "not a case" and the reverse mistake (dropping a real case) is
silent.
"""
from __future__ import annotations

import re
from typing import Optional

from .config import Settings
from .models import Email


def prefilter(email: Email, settings: Settings) -> Optional[str]:
    """Return the name of the rule that discards this email, or None to continue."""
    headers = {k.lower(): v.lower() for k, v in email.headers.items()}
    for h in settings.auto_reply_headers:
        if h in headers and headers[h] not in ("no", ""):
            return f"auto-reply header ({h})"

    sender = email.sender.lower()
    for prefix in settings.non_case_senders:
        if sender.startswith(prefix):
            return f"non-case sender ({prefix})"

    subject = email.subject.strip().lower()
    subject = re.sub(r"^((re|fw|fwd):\s*)+", "", subject)
    for pattern in settings.routine_subject_patterns:
        if re.search(pattern, subject):
            return f"routine subject ({pattern})"

    if not email.body.strip() and not email.subject.strip():
        return "empty message"
    return None
