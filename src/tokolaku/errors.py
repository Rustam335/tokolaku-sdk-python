"""Taxonomy error SDK Tokolaku — port dari `errors.ts` (referensi TS)."""

from __future__ import annotations

import json


class TokolakuAPIError(Exception):
    """Base error semua kegagalan API.

    `status` None = kegagalan sebelum ada respons HTTP (network/timeout).
    `code` = kode envelope BE, mis. "insufficient_balance"; None bila body
    bukan JSON envelope.
    """

    def __init__(self, message: str, *, status: int | None, code: str | None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class TokolakuAuthenticationError(TokolakuAPIError):
    """401."""


class TokolakuInsufficientBalanceError(TokolakuAPIError):
    """402."""


class TokolakuPermissionError(TokolakuAPIError):
    """403."""


class TokolakuRateLimitError(TokolakuAPIError):
    """429."""


class TokolakuValidationError(TokolakuAPIError):
    """400/422 + validasi klien."""


class TokolakuWebhookSignatureError(Exception):
    """Signature webhook tidak valid/hilang. TIDAK diturunkan dari TokolakuAPIError."""

    def __init__(self, message: str = "Signature webhook tidak valid") -> None:
        super().__init__(message)


_STATUS_CLASS: dict[int, type[TokolakuAPIError]] = {
    400: TokolakuValidationError,
    401: TokolakuAuthenticationError,
    402: TokolakuInsufficientBalanceError,
    403: TokolakuPermissionError,
    422: TokolakuValidationError,
    429: TokolakuRateLimitError,
}


def map_response_error(status: int, body_text: str) -> TokolakuAPIError:
    """Terjemahkan respons non-2xx jadi error class.

    Envelope BE: `{"error": {"code", "message"}}`. Body non-JSON dipotong
    500 char. Body kosong -> pesan "HTTP <status>".
    """
    code: str | None = None
    message = body_text[:500] if body_text else f"HTTP {status}"
    try:
        parsed = json.loads(body_text)
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if error and isinstance(error, dict):
            code_val = error.get("code")
            if code_val is not None:
                code = code_val
            msg_val = error.get("message")
            if msg_val is not None:
                message = msg_val
    except (json.JSONDecodeError, ValueError):
        pass  # non-JSON — pakai default

    cls = _STATUS_CLASS.get(status, TokolakuAPIError)
    return cls(message, status=status, code=code)
