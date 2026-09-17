"""Verifikasi & parsing webhook SDK Tokolaku — port dari `webhooks.ts` (referensi TS)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from .errors import TokolakuWebhookSignatureError

_SIGNATURE_PREFIX = "sha256="
_HEX_RE = re.compile(r"[0-9a-fA-F]{64}")


def verify_webhook_signature(
    raw_body: str | bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verifikasi header `x-tokolaku-signature` (format `sha256=<hex>`,
    HMAC-SHA256(secret, rawBody)) — compare timing-safe. `raw_body` HARUS
    bytes/str mentah persis seperti diterima (bukan hasil re-serialize).
    Hex format strict: `re.fullmatch` exactly 64 hex chars (case-insensitive),
    menolak trailing garbage (termasuk trailing "\\n"). Never-throw: input
    apa pun yang tidak valid mengembalikan False, bukan exception.
    """
    if not signature_header or not signature_header.startswith(_SIGNATURE_PREFIX):
        return False

    hex_part = signature_header[len(_SIGNATURE_PREFIX) :]
    if not _HEX_RE.fullmatch(hex_part):
        return False

    body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).digest()

    try:
        given = bytes.fromhex(hex_part)
    except ValueError:
        return False

    return hmac.compare_digest(given, expected)


def construct_event(
    raw_body: str | bytes,
    signature_header: str | None,
    secret: str,
) -> dict[str, Any]:
    """Verify + parse. Signature invalid -> raise TokolakuWebhookSignatureError.

    Signature VALID tapi `raw_body` bukan JSON valid -> `json.JSONDecodeError`
    dari `json.loads` (sengaja tidak dibungkus — itu bug payload, bukan soal
    keamanan).
    """
    if not verify_webhook_signature(raw_body, signature_header, secret):
        raise TokolakuWebhookSignatureError()
    return {"event": json.loads(raw_body)}


__all__ = [
    "TokolakuWebhookSignatureError",
    "construct_event",
    "verify_webhook_signature",
]
