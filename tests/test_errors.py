"""Tests untuk tokolaku.errors — port dari test/errors.test.ts (TS reference)."""

import json

import pytest

from tokolaku.errors import (
    TokolakuAPIError,
    TokolakuAuthenticationError,
    TokolakuInsufficientBalanceError,
    TokolakuPermissionError,
    TokolakuRateLimitError,
    TokolakuValidationError,
    TokolakuWebhookSignatureError,
    map_response_error,
)


def envelope(code: str, message: str) -> str:
    return json.dumps({"error": {"code": code, "message": message}})


def test_map_response_error_401_authentication_error_dengan_code_dari_envelope():
    e = map_response_error(401, envelope("invalid_key", "API key tidak valid"))
    assert isinstance(e, TokolakuAuthenticationError)
    assert isinstance(e, TokolakuAPIError)
    assert e.status == 401
    assert e.code == "invalid_key"
    assert str(e) == "API key tidak valid"


def test_map_response_error_mapping_kategori_lengkap():
    assert isinstance(map_response_error(400, envelope("invalid_body", "x")), TokolakuValidationError)
    assert isinstance(map_response_error(422, envelope("ai_not_configured", "x")), TokolakuValidationError)
    assert isinstance(
        map_response_error(402, envelope("insufficient_balance", "x")), TokolakuInsufficientBalanceError
    )
    assert isinstance(map_response_error(403, envelope("invalid_scope", "x")), TokolakuPermissionError)
    assert isinstance(map_response_error(429, envelope("quota_exceeded", "x")), TokolakuRateLimitError)


def test_map_response_error_500_dan_404_base_error_bukan_subclass():
    e = map_response_error(500, envelope("send_failed", "x"))
    assert type(e) is TokolakuAPIError
    e404 = map_response_error(404, "")
    assert e404.status == 404
    assert type(e404) is TokolakuAPIError


def test_map_response_error_body_non_json_code_none_message_dipotong_500_char():
    e = map_response_error(502, "Bad Gateway " + "y" * 600)
    assert e.code is None
    assert len(str(e)) <= 500


def test_map_response_error_body_kosong_message_http_status():
    e = map_response_error(503, "")
    assert str(e) == "HTTP 503"


def test_map_response_error_status_tak_dikenal_pakai_base_class():
    e = map_response_error(418, envelope("teapot", "aku teko"))
    assert type(e) is TokolakuAPIError
    assert e.status == 418
    assert e.code == "teapot"


def test_api_error_attrs_status_none_untuk_kegagalan_pra_respons():
    e = TokolakuAPIError("network gagal", status=None, code="network_error")
    assert e.status is None
    assert e.code == "network_error"
    assert str(e) == "network gagal"


def test_webhook_signature_error_default_message():
    e = TokolakuWebhookSignatureError()
    assert str(e) == "Signature webhook tidak valid"
    assert not isinstance(e, TokolakuAPIError)


def test_webhook_signature_error_custom_message():
    e = TokolakuWebhookSignatureError("custom")
    assert str(e) == "custom"


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (401, TokolakuAuthenticationError),
        (402, TokolakuInsufficientBalanceError),
        (403, TokolakuPermissionError),
        (429, TokolakuRateLimitError),
        (400, TokolakuValidationError),
        (422, TokolakuValidationError),
    ],
)
def test_map_response_error_status_class_table(status, cls):
    e = map_response_error(status, envelope("c", "m"))
    assert isinstance(e, cls)
    assert e.status == status
