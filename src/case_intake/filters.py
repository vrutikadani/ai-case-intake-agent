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


_DISPUTE = re.compile(r"\b(dispute|overcharg|short[- ]?pa|on hold|hold(ing)? (the )?payment|can(no|')t pay|unable to pay|"
                      r"wrong|incorrect|reject|missing|discrepanc|damaged|not received|credit hold)", re.I)


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
    # Subject rules only apply to original messages. A person replying to a
    # remittance or a report ("RE: Remittance advice ...") may be raising the
    # very issue we want; the classifier decides those.
    # Subject rules also stand down when the body uses dispute language, so
    # "Payment received for SO 38262" with "you overcharged us" reaches the model.
    if not re.match(r"^(re|fw|fwd):", subject) and not _DISPUTE.search(email.body):
        for pattern in settings.routine_subject_patterns:
            if re.search(pattern, subject):
                return f"routine subject ({pattern})"

    if not email.body.strip() and not email.subject.strip():
        return "empty message"
    return None
