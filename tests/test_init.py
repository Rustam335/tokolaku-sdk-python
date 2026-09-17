"""Sanity test untuk permukaan ekspor paket `tokolaku` (Task PY4)."""

from __future__ import annotations

import tokolaku
from tokolaku import webhooks
from tokolaku.webhooks import verify_webhook_signature


def test_top_level_exports_present() -> None:
    expected_names = [
        "Tokolaku",
        "TokolakuAPIError",
        "TokolakuAuthenticationError",
        "TokolakuInsufficientBalanceError",
        "TokolakuPermissionError",
        "TokolakuRateLimitError",
        "TokolakuValidationError",
        "TokolakuWebhookSignatureError",
        "BotReply",
        "SentMessage",
        "construct_event",
        "verify_webhook_signature",
        "webhooks",
        "__version__",
    ]
    for name in expected_names:
        assert hasattr(tokolaku, name), f"tokolaku.{name} tidak ter-export"


def test_webhooks_submodule_importable() -> None:
    assert callable(webhooks.verify_webhook_signature)
    assert callable(webhooks.construct_event)
    assert webhooks.verify_webhook_signature is verify_webhook_signature


def test_version_is_string() -> None:
    assert isinstance(tokolaku.__version__, str)
    assert tokolaku.__version__ == "1.0.0"
