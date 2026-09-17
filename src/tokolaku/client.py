"""Klien SDK Tokolaku — port dari `client.ts` (referensi TS)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from tokolaku.errors import TokolakuAPIError, TokolakuValidationError, map_response_error
from tokolaku.retry import RetryPolicy, retry_delay_ms, should_retry
from tokolaku.types import BotReply, SentMessage

DEFAULT_BASE_URL = "https://api.tokolaku.id"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2


class Tokolaku:
    """Klien SDK Tokolaku Engine API.

    Konstruktor menerima api key sebagai positional string ATAU kwarg
    `api_key=` (padanan `apiKeyOrOptions: string | TokolakuOptions` di TS).
    """

    def __init__(
        self,
        api_key_or_none: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ) -> None:
        resolved_key = api_key_or_none if api_key_or_none is not None else api_key
        if not resolved_key:
            raise TokolakuValidationError(
                "api_key wajib diisi", status=None, code="missing_api_key"
            )
        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._http_client = http_client if http_client is not None else httpx.Client()
        self.messages = _MessagesAPI(self)

    def bot_reply(
        self,
        message: str,
        session_id: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> BotReply:
        """Balasan AI bot tenant untuk satu pesan pelanggan (POST /api/v1/bot/reply)."""
        body: dict[str, Any] = {"message": message}
        if session_id is not None:
            body["session_id"] = session_id
        if history is not None:
            body["history"] = history
        data = self._request("/api/v1/bot/reply", body, "bot_reply")
        return BotReply(reply=data["reply"], parts=list(data["parts"]))

    def _request(self, path: str, body: dict[str, Any], policy: RetryPolicy) -> dict[str, Any]:
        last_error: TokolakuAPIError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._once(path, body)
            except TokolakuAPIError as err:
                last_error = err
                if attempt >= self._max_retries or not should_retry(policy, err):
                    raise
                retry_after_sec = getattr(err, "retry_after_sec", None)
                time.sleep(retry_delay_ms(attempt, retry_after_sec) / 1000)
        # Tidak pernah tercapai — loop di atas selalu return atau raise.
        assert last_error is not None
        raise last_error

    def _once(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        try:
            response = self._http_client.post(url, headers=headers, json=body, timeout=self._timeout)
        except httpx.TimeoutException as e:
            raise TokolakuAPIError(
                f"Timeout setelah {int(self._timeout * 1000)}ms", status=None, code="timeout"
            ) from e
        except httpx.RequestError as e:
            raise TokolakuAPIError(f"Network error: {e}", status=None, code="network_error") from e

        try:
            text = response.text
        except Exception as e:
            # Header respons SUDAH diterima (request sampai server, efek samping —
            # mis. pesan terkirim & tercharge, reply AI dihasilkan — mungkin sudah
            # terjadi) tapi baca body gagal. BUKAN network error & TIDAK boleh
            # di-retry (lihat should_retry: sejajar dengan invalid_response).
            raise TokolakuAPIError(
                "Gagal membaca body respons", status=response.status_code, code="response_read_error"
            ) from e

        if not (200 <= response.status_code < 300):
            ra_header = response.headers.get("retry-after")
            retry_after_sec = int(ra_header) if ra_header is not None and ra_header.isdigit() else None
            err = map_response_error(response.status_code, text)
            err.retry_after_sec = retry_after_sec  # type: ignore[attr-defined]
            raise err

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Respons HTTP sudah diterima (efek samping server, mis. pesan terkirim &
            # tercharge, SUDAH terjadi) — parse gagal BUKAN network error & TIDAK
            # boleh di-retry.
            raise TokolakuAPIError(
                "Respons server bukan JSON valid", status=response.status_code, code="invalid_response"
            ) from e


class _MessagesAPI:
    """Aksesor `client.messages.send(...)` — padanan `readonly messages = {...}` di TS."""

    def __init__(self, client: Tokolaku) -> None:
        self._client = client

    def send(
        self,
        to: str,
        text: str | None = None,
        template: dict[str, Any] | None = None,
        channel_id: str | None = None,
        country_code: str | None = None,
    ) -> SentMessage:
        """Kirim pesan text/template via channel resmi (POST /api/v1/messages).

        `type` diinferensi: `text` -> "text", `template` -> "template".
        """
        has_text = text is not None
        has_template = template is not None
        if has_text == has_template:
            raise TokolakuValidationError(
                "Isi tepat satu: `text` (pesan sesi) ATAU `template` (business-initiated)",
                status=None,
                code="invalid_params",
            )
        body: dict[str, Any] = {"to": to, "type": "text" if has_text else "template"}
        if has_text:
            body["text"] = text
        if has_template:
            body["template"] = template
        if channel_id is not None:
            body["channel_id"] = channel_id
        if country_code is not None:
            body["country_code"] = country_code
        data = self._client._request("/api/v1/messages", body, "messages")
        return SentMessage(
            id=data["id"],
            channel_id=data["channel_id"],
            to=data["to"],
            type=data["type"],
            status=data["status"],
            provider_message_id=data.get("provider_message_id"),
            charged_idr=data["charged_idr"],
        )
