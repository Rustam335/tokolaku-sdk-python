"""Tests retry-flow end-to-end tokolaku.client — port dari test/retry.test.ts (TS reference).

Mencakup semua baris tabel retry uang-sadar per endpoint (bot_reply vs messages),
nol network via httpx.MockTransport. time.sleep di-patch no-op — durasi delay
sudah diverifikasi terpisah di tests/test_retry.py (retry_delay_ms).
"""

from __future__ import annotations

import httpx
import pytest

from tokolaku.client import Tokolaku
from tokolaku.errors import TokolakuAPIError, TokolakuRateLimitError


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("tokolaku.client.time.sleep", lambda _seconds: None)


class _RaisingStream(httpx.SyncByteStream):
    """Stream yang yield sebagian body lalu raise httpx.ReadError — simulasi
    koneksi terputus SETELAH header respons sudah diterima (mid-body failure).
    """

    def __iter__(self):
        yield b'{"reply": "seba'
        raise httpx.ReadError("connection reset mid-body")

    def close(self) -> None:
        pass


def seq_client(steps, **kwargs):
    """steps: list of "network" | "timeout" | (status, body_dict|raw_str)."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(len(calls), len(steps) - 1)
        calls.append(request)
        step = steps[idx]
        if step == "network":
            raise httpx.ConnectError("connection refused", request=request)
        if step == "timeout":
            raise httpx.TimeoutException("timed out", request=request)
        status, payload = step
        if isinstance(payload, str):
            return httpx.Response(status, content=payload)
        return httpx.Response(status, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    max_retries = kwargs.pop("max_retries", 2)
    tk = Tokolaku(api_key="k", http_client=http_client, max_retries=max_retries, **kwargs)
    return tk, calls


OK_REPLY = (200, {"reply": "ok", "parts": ["ok"]})
OK_MSG = (
    200,
    {
        "id": "m",
        "channel_id": "c",
        "to": "628",
        "type": "text",
        "status": "sent",
        "provider_message_id": None,
        "charged_idr": 0,
    },
)
ERR_429 = (429, {"error": {"code": "rate_limited", "message": "pelan-pelan"}})
ERR_503 = (503, {"error": {"code": "unavailable", "message": "sebentar"}})
MALFORMED_JSON = (200, "{not valid json")


def test_bot_reply_429_lalu_sukses_di_retry_2_panggilan():
    tk, calls = seq_client([ERR_429, OK_REPLY])
    res = tk.bot_reply(message="hai")
    assert res.reply == "ok"
    assert len(calls) == 2


def test_bot_reply_503_dan_network_error_di_retry_3_panggilan():
    tk, calls = seq_client([ERR_503, "network", OK_REPLY])
    tk.bot_reply(message="hai")
    assert len(calls) == 3


def test_bot_reply_max_retries_dihormati_raises_rate_limit_3_panggilan():
    tk, calls = seq_client([ERR_429])
    with pytest.raises(TokolakuRateLimitError):
        tk.bot_reply(message="hai")
    assert len(calls) == 3  # 1 asli + 2 retry


def test_messages_send_429_dan_network_di_retry_3_panggilan():
    tk, calls = seq_client([ERR_429, "network", OK_MSG])
    tk.messages.send(to="628", text="hai")
    assert len(calls) == 3


def test_messages_send_503_tidak_di_retry_1_panggilan():
    tk, calls = seq_client([ERR_503, OK_MSG])
    with pytest.raises(TokolakuAPIError):
        tk.messages.send(to="628", text="hai")
    assert len(calls) == 1


def test_timeout_tidak_di_retry_kedua_endpoint_code_timeout():
    tk1, calls1 = seq_client(["timeout", OK_REPLY])
    with pytest.raises(TokolakuAPIError) as exc1:
        tk1.bot_reply(message="x")
    assert exc1.value.code == "timeout"
    assert exc1.value.status is None
    assert len(calls1) == 1

    tk2, calls2 = seq_client(["timeout", OK_MSG])
    with pytest.raises(TokolakuAPIError) as exc2:
        tk2.messages.send(to="628", text="x")
    assert exc2.value.code == "timeout"
    assert exc2.value.status is None
    assert len(calls2) == 1


def test_body_2xx_json_rusak_tidak_di_retry_kedua_endpoint_invalid_response():
    tk1, calls1 = seq_client([MALFORMED_JSON, OK_MSG])
    with pytest.raises(TokolakuAPIError) as exc1:
        tk1.messages.send(to="628", text="hai")
    assert exc1.value.code == "invalid_response"
    assert exc1.value.status == 200
    assert len(calls1) == 1

    tk2, calls2 = seq_client([MALFORMED_JSON, OK_REPLY])
    with pytest.raises(TokolakuAPIError) as exc2:
        tk2.bot_reply(message="hai")
    assert exc2.value.code == "invalid_response"
    assert exc2.value.status == 200
    assert len(calls2) == 1


def _mid_body_failure_client(**kwargs):
    """Client yang SELALU balas header 200 lalu putus koneksi di tengah body —
    dipakai untuk kedua endpoint karena kegagalannya terjadi sebelum body
    di-parse (sebelum tahu endpoint mana yang dipanggil)."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=_RaisingStream(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    max_retries = kwargs.pop("max_retries", 2)
    tk = Tokolaku(api_key="k", http_client=http_client, max_retries=max_retries, **kwargs)
    return tk, calls


def test_mid_body_failure_bot_reply_1_panggilan_response_read_error():
    """Header 200 sudah diterima, request SAMPAI server (efek samping mungkin
    sudah terjadi) — kegagalan baca body TIDAK BOLEH jadi network_error yang
    di-retry (celah double-send)."""
    tk, calls = _mid_body_failure_client()
    with pytest.raises(TokolakuAPIError) as exc:
        tk.bot_reply(message="hai")
    assert exc.value.code == "response_read_error"
    assert exc.value.status == 200
    assert len(calls) == 1


def test_mid_body_failure_messages_send_1_panggilan_response_read_error():
    tk, calls = _mid_body_failure_client()
    with pytest.raises(TokolakuAPIError) as exc:
        tk.messages.send(to="628", text="hai")
    assert exc.value.code == "response_read_error"
    assert exc.value.status == 200
    assert len(calls) == 1


def test_retry_after_header_malformed_unicode_digit_tidak_crash():
    """`"²".isdigit()` True di Python tapi `int("²")` raise ValueError — header
    Retry-After semacam ini harus di-treat sebagai "tidak ada" (fallback ke
    backoff jitter), bukan meng-crash request dengan ValueError yang tidak
    tertangkap."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Header dikirim sbg raw bytes (spt di wire) supaya lolos httpx ascii-encode
        # guard di sisi konstruksi — "²" (U+00B2, superscript two, non-ASCII).
        return httpx.Response(
            429,
            headers=[(b"retry-after", "²".encode("latin-1"))],
            json={"error": {"code": "rate_limited", "message": "pelan-pelan"}},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    tk = Tokolaku(api_key="k", http_client=http_client, max_retries=0)
    with pytest.raises(TokolakuRateLimitError):
        tk.bot_reply(message="hai")
