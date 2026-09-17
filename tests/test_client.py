"""Tests untuk tokolaku.client — port dari test/client.test.ts (TS reference).

Nol network: seluruh request lewat httpx.MockTransport (injeksi http_client).
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest

from tokolaku.client import Tokolaku
from tokolaku.errors import TokolakuAuthenticationError, TokolakuValidationError


def make_client(responses, **kwargs):
    """responses: list[(status, body_dict)]. Response terakhir dipakai berulang."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        idx = min(len(calls) - 1, len(responses) - 1)
        status, body = responses[idx]
        return httpx.Response(status, json=body)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    api_key = kwargs.pop("api_key", "tk_test_sk_abc")
    tk = Tokolaku(api_key=api_key, http_client=http_client, **kwargs)
    return tk, calls


def test_bot_reply_url_header_body_benar():
    tk, calls = make_client([(200, {"reply": "Halo!", "parts": ["Halo!"]})])
    res = tk.bot_reply(message="halo", session_id="s1")
    assert res.reply == "Halo!"
    assert res.parts == ["Halo!"]
    assert str(calls[0].url) == "https://api.tokolaku.id/api/v1/bot/reply"
    assert calls[0].headers["authorization"] == "Bearer tk_test_sk_abc"
    assert calls[0].headers["content-type"] == "application/json"
    assert json.loads(calls[0].content) == {"message": "halo", "session_id": "s1"}


def test_messages_send_text_infer_type_text():
    tk, calls = make_client(
        [
            (
                200,
                {
                    "id": "m1",
                    "channel_id": "c1",
                    "to": "628",
                    "type": "text",
                    "status": "sent",
                    "provider_message_id": None,
                    "charged_idr": 0,
                },
            )
        ]
    )
    res = tk.messages.send(to="628", text="hai")
    assert res.status == "sent"
    assert str(calls[0].url) == "https://api.tokolaku.id/api/v1/messages"
    assert json.loads(calls[0].content) == {"to": "628", "type": "text", "text": "hai"}


def test_messages_send_template_infer_type_template_dan_field_diteruskan():
    tk, calls = make_client(
        [
            (
                200,
                {
                    "id": "m2",
                    "channel_id": "c1",
                    "to": "628",
                    "type": "template",
                    "status": "sent",
                    "provider_message_id": "wamid.x",
                    "charged_idr": 350,
                },
            )
        ]
    )
    tk.messages.send(
        to="628",
        template={"name": "order_update", "language": "id", "category": "utility"},
        channel_id="ch1",
        country_code="ID",
    )
    assert json.loads(calls[0].content) == {
        "to": "628",
        "type": "template",
        "template": {"name": "order_update", "language": "id", "category": "utility"},
        "channel_id": "ch1",
        "country_code": "ID",
    }


def test_messages_send_text_dan_template_bersamaan_atau_kosong_raises_sebelum_http():
    tk, calls = make_client([(200, {})])
    with pytest.raises(TokolakuValidationError):
        tk.messages.send(
            to="628",
            text="x",
            template={"name": "n", "language": "id", "category": "utility"},
        )
    with pytest.raises(TokolakuValidationError):
        tk.messages.send(to="628")
    assert len(calls) == 0


def test_error_respons_dipetakan_ke_class_401_authentication():
    tk, _calls = make_client(
        [(401, {"error": {"code": "invalid_key", "message": "API key tidak valid"}})]
    )
    with pytest.raises(TokolakuAuthenticationError) as exc_info:
        tk.bot_reply(message="hai")
    assert exc_info.value.code == "invalid_key"


def test_konstruktor_string_positional_valid():
    tk = Tokolaku("tk_live_sk_x")
    assert isinstance(tk, Tokolaku)


def test_base_url_custom_dipakai():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"reply": "ok", "parts": ["ok"]})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    tk = Tokolaku(api_key="k", base_url="http://localhost:3011", http_client=http_client)
    tk.bot_reply(message="hai")
    assert str(calls[0].url) == "http://localhost:3011/api/v1/bot/reply"


def test_konstruktor_tanpa_api_key_raises_validation_error():
    with pytest.raises(TokolakuValidationError):
        Tokolaku()


def test_bot_reply_result_frozen_dataclass_tidak_bisa_diubah():
    tk, _calls = make_client([(200, {"reply": "Halo!", "parts": ["Halo!"]})])
    res = tk.bot_reply(message="halo")
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.reply = "diubah paksa"  # type: ignore[misc]
