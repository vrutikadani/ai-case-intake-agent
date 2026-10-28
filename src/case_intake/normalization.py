"""Exact identifier handling. None of this is left to the model.

The model is good at finding "the order number" in messy text and bad at
producing the same string twice. Everything that has to be exact (what counts
as the same order, the case key, whether an identifier is real) is decided
here, by code that returns the same answer every time.
"""
from __future__ import annotations

import re
from typing import Optional

# Prefixes people actually type in front of identifiers.
_ORDER_PREFIX = re.compile(r"^\s*(so|sales\s*order|order|ord|po|inv|invoice)\s*(no\.?|number)?\s*[#:.\-]?\s*",
                           re.IGNORECASE)
_CUSTOMER_PREFIX = re.compile(r"^\s*(c|cust|customer|acct|account)\s*(no\.?|number|id)?\s*[#:.\-]?\s*",
                              re.IGNORECASE)

ORDER_MIN_DIGITS, ORDER_MAX_DIGITS = 4, 10
CUSTOMER_MIN_DIGITS, CUSTOMER_MAX_DIGITS = 4, 8


def _digits_core(raw: str, prefix: re.Pattern, lo: int, hi: int) -> Optional[str]:
    s = prefix.sub("", raw.strip())
    s = re.sub(r"[\s\-]", "", s)
    if not s.isdigit():
        return None            # letters left over = not an identifier we trust
    s = s.lstrip("0")
    if not (lo <= len(s) <= hi):
        return None
    return s


def normalize_order_id(raw: Optional[str]) -> Optional[str]:
    """'SO#038262', 'so 38262', '038262' -> '38262'. Malformed -> None."""
    if raw is None:
        return None
    return _digits_core(str(raw), _ORDER_PREFIX, ORDER_MIN_DIGITS, ORDER_MAX_DIGITS)


def normalize_customer_id(raw: Optional[str]) -> Optional[str]:
    """'C-010442', 'Cust #10442', '10442' -> '10442'. Malformed -> None."""
    if raw is None:
        return None
    return _digits_core(str(raw), _CUSTOMER_PREFIX, CUSTOMER_MIN_DIGITS, CUSTOMER_MAX_DIGITS)


def case_key(customer_id: str, order_id: str) -> str:
    """The single identity used for matching and duplicate prevention."""
    return f"{customer_id}|{order_id}"


def grounded(normalized_id: Optional[str], email_text: str) -> bool:
    """True if the identifier actually appears in the email.

    The classifier may hallucinate an identifier, or be steered into one by text
    inside the email. An identifier counts only if the same digits occur in the
    message as a standalone number (leading zeros and prefixes allowed).
    """
    if not normalized_id:
        return False
    pattern = rf"(?<!\d)0*{re.escape(normalized_id)}(?!\d)"
    return re.search(pattern, email_text) is not None
