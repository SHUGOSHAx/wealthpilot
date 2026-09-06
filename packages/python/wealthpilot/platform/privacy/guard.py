"""Small, deterministic privacy gate for the MVP model boundary.

The gateway accepts only public research facts and a deliberately narrow set of
anonymous aggregate financial metrics.  This module never tries to make raw P2
records safe: raw transactions, account identifiers and holdings are rejected.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


class PrivacyBoundaryError(ValueError):
    """Raised before a payload containing P2/P3 data reaches a model adapter."""


_FORBIDDEN_KEYS = {
    "account",
    "account_id",
    "account_number",
    "account_balances",
    "api_key",
    "bank_card",
    "broker_credential",
    "card_number",
    "credential",
    "description",
    "descriptions",
    "holdings",
    "identity_number",
    "password",
    "raw_rows",
    "secret",
    "signing_key",
    "token",
    "transaction",
    "transaction_description",
    "transactions",
}

_P3_PATTERNS = (
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\b(?:sk|api)[-_][A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:password|passwd|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
)


def assert_model_safe(payload: Any, *, privacy_level: str) -> None:
    """Reject P3 and raw P2 content before it is captured or dispatched."""

    if privacy_level.upper() == "P3":
        raise PrivacyBoundaryError("P3 content is forbidden at the model gateway")
    if privacy_level.upper() not in {"P0", "P1"}:
        raise PrivacyBoundaryError("model requests must be minimized to P0/P1")
    _scan(payload, path="$", seen=set())


def _scan(value: Any, *, path: str, seen: set[int]) -> None:
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).lower()
            if key in _FORBIDDEN_KEYS or any(part in _FORBIDDEN_KEYS for part in key.split(".")):
                raise PrivacyBoundaryError(f"forbidden P2/P3 field at {path}.{raw_key}")
            _scan(item, path=f"{path}.{raw_key}", seen=seen)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _scan(item, path=f"{path}[{index}]", seen=seen)
    elif isinstance(value, str):
        for pattern in _P3_PATTERNS:
            if pattern.search(value):
                raise PrivacyBoundaryError(f"probable P3 value at {path}")
