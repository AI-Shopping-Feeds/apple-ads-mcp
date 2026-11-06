"""Scrub credentials from anything that might be logged, audited or returned.

Apple Ads access tokens and client secrets are JWT/JWE strings starting with
`eyJ`. Private keys are PEM blocks. Both are replaced wherever they appear, and
values under credential-like keys are replaced whatever they look like.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SECRET_KEYS = {
    "access_token",
    "accesstoken",
    "authorization",
    "client_secret",
    "clientsecret",
    "private_key",
    "privatekey",
    "refresh_token",
    "token",
    "password",
}

# JWT / JWE compact serialisations (header segment starts with base64url '{"').
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{4,}(?:\.[A-Za-z0-9_-]*){1,4}")
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact_text(text: str) -> str:
    text = _PEM_RE.sub(REDACTED, text)
    text = _BEARER_RE.sub(lambda m: m.group(1) + REDACTED, text)
    return _JWT_RE.sub(REDACTED, text)


def redact(value: Any) -> Any:
    """Return a copy of `value` with secrets replaced. Leaves non-secret data intact."""
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.replace("-", "_").lower() in _SECRET_KEYS:
                out[k] = REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
