"""TDD tests untuk `tokolaku.webhooks` — port dari `test/webhooks.test.ts`."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tokolaku.errors import TokolakuWebhookSignatureError
from tokolaku.webhooks import construct_event, verify_webhook_signature

SECRET = "whsec_rahasia_123"
BODY = json.dumps({"event": "message.received", "data": {"text": "halo kak"}})


def sign(secret: str, body: str | bytes) -> str:
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_valid_signature_returns_true() -> None:
    assert verify_webhook_signature(BODY, sign(SECRET, BODY), SECRET) is True


def test_verify_valid_signature_with_bytes_body_returns_true() -> None:
    body_bytes = BODY.encode("utf-8")
    assert verify_webhook_signature(body_bytes, sign(SECRET, body_bytes), SECRET) is True


def test_verify_wrong_secret_returns_false() -> None:
    assert verify_webhook_signature(BODY, sign("salah", BODY), SECRET) is False


def test_verify_body_diubah_returns_false() -> None:
    assert verify_webhook_signature(BODY + "x", sign(SECRET, BODY), SECRET) is False


def test_verify_tanpa_prefix_returns_false() -> None:
    raw_sig = sign(SECRET, BODY)[len("sha256="):]
    assert verify_webhook_signature(BODY, raw_sig, SECRET) is False


def test_verify_none_header_returns_false() -> None:
    assert verify_webhook_signature(BODY, None, SECRET) is False


def test_verify_trailing_garbage_zz_returns_false() -> None:
    assert verify_webhook_signature(BODY, sign(SECRET, BODY) + "zz", SECRET) is False


def test_verify_short_garbage_hex_returns_false_no_throw() -> None:
    # panjang beda dari 64 hex chars — tidak boleh throw
    assert verify_webhook_signature(BODY, "sha256=zzzz", SECRET) is False


def test_verify_trailing_newline_after_valid_hex_returns_false() -> None:
    # fullmatch tidak vulnerable ke trailing-\n seperti PCRE $, tapi tetap
    # ditest eksplisit sesuai temuan port PHP.
    assert verify_webhook_signature(BODY, sign(SECRET, BODY) + "\n", SECRET) is False


def test_verify_uppercase_hex_valid_returns_true() -> None:
    valid_sig = sign(SECRET, BODY)
    upper = "sha256=" + valid_sig[len("sha256="):].upper()
    assert verify_webhook_signature(BODY, upper, SECRET) is True


def test_verify_never_throws_on_malformed_input() -> None:
    # Berbagai input aneh — semua harus mengembalikan False, tidak throw.
    assert verify_webhook_signature(BODY, "", SECRET) is False
    assert verify_webhook_signature(BODY, "sha256=", SECRET) is False
    assert verify_webhook_signature(BODY, "not-even-close", SECRET) is False


def test_construct_event_valid_parses_body() -> None:
    result = construct_event(BODY, sign(SECRET, BODY), SECRET)
    assert result["event"]["event"] == "message.received"
    assert result["event"]["data"]["text"] == "halo kak"


def test_construct_event_invalid_signature_raises() -> None:
    with pytest.raises(TokolakuWebhookSignatureError):
        construct_event(BODY, "sha256=" + "de" * 32, SECRET)


def test_construct_event_missing_signature_raises() -> None:
    with pytest.raises(TokolakuWebhookSignatureError):
        construct_event(BODY, None, SECRET)


def test_construct_event_valid_signature_but_non_json_body_raises_json_decode_error() -> None:
    raw = "bukan json"
    with pytest.raises(json.JSONDecodeError):
        construct_event(raw, sign(SECRET, raw), SECRET)
