"""Tests untuk tokolaku.retry — port dari test/retry.test.ts (TS reference),
mencakup SEMUA sel tabel retry uang-sadar di spec Kontrak inti."""

import pytest

from tokolaku.errors import TokolakuAPIError
from tokolaku.retry import retry_delay_ms, should_retry


def err(status, code):
    return TokolakuAPIError("x", status=status, code=code)


# --- should_retry: tabel lengkap, kedua policy ---

@pytest.mark.parametrize("policy", ["bot_reply", "messages"])
def test_429_selalu_retry_kedua_policy(policy):
    assert should_retry(policy, err(429, "rate_limited")) is True


def test_5xx_retry_hanya_bot_reply():
    assert should_retry("bot_reply", err(500, "send_failed")) is True
    assert should_retry("bot_reply", err(503, "unavailable")) is True


def test_5xx_tidak_retry_messages():
    assert should_retry("messages", err(500, "send_failed")) is False
    assert should_retry("messages", err(503, "unavailable")) is False


@pytest.mark.parametrize("policy", ["bot_reply", "messages"])
def test_network_error_pra_respons_selalu_retry(policy):
    assert should_retry(policy, err(None, "network_error")) is True


@pytest.mark.parametrize("policy", ["bot_reply", "messages"])
def test_timeout_tidak_pernah_retry(policy):
    assert should_retry(policy, err(None, "timeout")) is False
    # timeout menang bahkan jika status kebetulan diisi (defensif)
    assert should_retry(policy, err(500, "timeout")) is False


@pytest.mark.parametrize("policy", ["bot_reply", "messages"])
def test_invalid_response_tidak_pernah_retry(policy):
    assert should_retry(policy, err(200, "invalid_response")) is False


@pytest.mark.parametrize("policy", ["bot_reply", "messages"])
def test_response_read_error_tidak_pernah_retry(policy):
    assert should_retry(policy, err(200, "response_read_error")) is False


def test_4xx_selain_429_tidak_retry_kedua_policy():
    assert should_retry("bot_reply", err(400, "invalid_body")) is False
    assert should_retry("messages", err(401, "invalid_key")) is False
    assert should_retry("bot_reply", err(403, "invalid_scope")) is False
    assert should_retry("messages", err(422, "ai_not_configured")) is False


# --- retry_delay_ms ---

def test_retry_after_menang_atas_backoff():
    assert retry_delay_ms(0, 3) == 3000
    assert retry_delay_ms(5, 0) == 0


def test_retry_after_none_pakai_backoff_jitter_dalam_batas():
    for attempt in range(6):
        d = retry_delay_ms(attempt, None)
        assert 125 <= d <= 1000, f"delay {d} attempt {attempt} di luar [125,1000]"


def test_retry_delay_cap_1000ms_pada_attempt_besar():
    d = retry_delay_ms(10, None)
    assert d <= 1000
