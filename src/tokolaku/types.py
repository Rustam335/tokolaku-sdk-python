"""Tipe respons SDK Tokolaku — port dari `types.ts` (referensi TS)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotReply:
    """Respons `POST /api/v1/bot/reply`."""

    reply: str
    parts: list[str]


@dataclass(frozen=True)
class SentMessage:
    """Respons `POST /api/v1/messages`."""

    id: str
    channel_id: str
    to: str
    type: str
    status: str
    provider_message_id: str | None
    charged_idr: int
