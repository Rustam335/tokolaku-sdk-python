"""Kebijakan retry uang-sadar — port dari `retry.ts` (referensi TS)."""

from __future__ import annotations

import random
from typing import Literal

from tokolaku.errors import TokolakuAPIError

RetryPolicy = Literal["bot_reply", "messages"]


def should_retry(policy: RetryPolicy, error: TokolakuAPIError) -> bool:
    """Retry uang-sadar.

    - bot_reply: 429, 5xx, network error (tanpa efek samping bila gagal).
    - messages: HANYA 429 + network error pra-respons (pesan mungkin sudah
      terkirim & tercharge pada timeout/5xx — API belum punya idempotency
      key).
    - timeout (code "timeout") TIDAK pernah di-retry.
    """
    if error.code == "timeout":
        return False
    if error.status == 429:
        return True
    # "invalid_response" (200 OK tapi body JSON rusak) dan "response_read_error"
    # (header respons sudah diterima tapi baca body gagal) SENGAJA tidak match
    # rule apa pun di bawah ini — efek samping server sudah terjadi, jadi
    # non-retryable untuk kedua policy.
    if error.code == "network_error":
        return True
    if policy == "bot_reply" and error.status is not None and error.status >= 500:
        return True
    return False


def retry_delay_ms(attempt: int, retry_after_sec: int | None) -> int:
    """Exponential backoff + full jitter, base 250ms cap 1s; Retry-After menang."""
    if retry_after_sec is not None:
        return max(0, retry_after_sec * 1000)
    cap = min(1000, 250 * 2**attempt)
    return round(cap * (0.5 + random.random() * 0.5))
