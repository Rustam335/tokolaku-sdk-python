# tokolaku

Official Python SDK for the [Tokolaku Engine API](https://tokolaku.id/developers) — AI bot replies, omnichannel messaging (WhatsApp/Instagram/Messenger), and webhook verification.

## Install

```bash
pip install tokolaku
```

## Requirements

- Python >= 3.10

## Quickstart

*Bahasa Indonesia ringkas: buat instance `Tokolaku` dengan API key, lalu panggil `bot_reply` untuk balasan AI atau `messages.send` untuk kirim pesan lewat channel resmi (WhatsApp/Instagram/Messenger) yang sudah terhubung.*

```python
import os
from tokolaku import Tokolaku

tokolaku = Tokolaku(os.environ["TOKOLAKU_API_KEY"])
# or with options: Tokolaku(api_key=..., base_url=..., timeout=30.0, max_retries=2)

# 1. AI bot reply for a single customer message
reply = tokolaku.bot_reply(
    "Halo, apakah produk ini ready stock?",
    session_id="wa:628123456789",  # keeps multi-turn context
)
print(reply.reply, reply.parts)

# 2. Send a text message through a connected channel
sent = tokolaku.messages.send(
    to="628123456789",
    text="Terima kasih sudah menghubungi kami!",
    channel_id="ch_abc123",
)
print(sent.id, sent.status)
```

`messages.send` also accepts a business-initiated template message — pass `template` instead of `text` (exactly one of the two, never both):

```python
tokolaku.messages.send(
    to="628123456789",
    template={"name": "order_update", "language": "id", "category": "utility"},
    channel_id="ch_abc123",
)
```

## Error handling

Every failed request raises an instance of `TokolakuAPIError` (or one of its subclasses). `.status` is `None` when the request never got an HTTP response (network error, timeout); `.code` is the backend's machine-readable error code when available.

| Class | HTTP status | When it's raised |
|---|---|---|
| `TokolakuValidationError` | 400, 422 | Invalid request params — also raised client-side before any network call (e.g. `messages.send` with both `text` and `template`, or neither) |
| `TokolakuAuthenticationError` | 401 | Missing or invalid API key |
| `TokolakuInsufficientBalanceError` | 402 | Tenant balance too low to cover the charge |
| `TokolakuPermissionError` | 403 | API key lacks permission for this action |
| `TokolakuRateLimitError` | 429 | Rate limit exceeded |
| `TokolakuAPIError` | any other status, or `None` | Base class — also covers network errors, timeouts, and malformed responses not mapped above |
| `TokolakuWebhookSignatureError` | — | Webhook signature missing or invalid (does **not** extend `TokolakuAPIError`) |

```python
from tokolaku import (
    Tokolaku,
    TokolakuAPIError,
    TokolakuInsufficientBalanceError,
    TokolakuRateLimitError,
)

tokolaku = Tokolaku(os.environ["TOKOLAKU_API_KEY"])

try:
    tokolaku.bot_reply("Halo")
except TokolakuInsufficientBalanceError:
    ...  # top up balance, notify the tenant
except TokolakuRateLimitError:
    ...  # back off and retry later
except TokolakuAPIError as err:
    print(err.status, err.code, err)
```

## Retry policy

The SDK retries automatically (`max_retries`, default `2`) using exponential backoff with full jitter (base 250ms, capped at 1s; a `Retry-After` response header wins when present). The policy is **money-aware**: it only retries when a retry cannot cause a duplicate side effect.

| Condition | `bot_reply` | `messages.send` |
|---|---|---|
| `429 Too Many Requests` | Retried | Retried |
| Network error (request never got a response) | Retried | Retried |
| `5xx` server error | Retried | **Not** retried |
| Timeout (`code: "timeout"`) | **Not** retried | **Not** retried |
| `2xx` with malformed JSON body (`code: "invalid_response"`) | **Not** retried | **Not** retried |
| `2xx` where the body stream fails mid-read (`code: "response_read_error"`) | **Not** retried | **Not** retried |

- `bot_reply` has no side effect if it fails, so it retries on `429`, any `5xx`, and network errors.
- **`messages.send` is NOT retried on timeout/5xx because the message may already have been sent** and charged even though the client never saw a successful response, and the API does not yet expose an idempotency key. It only retries on `429` and network errors — a network retry only applies when the request itself failed before any response headers arrived (no response headers were ever received, so nothing could have been sent). Once response headers have arrived, a failure reading the body is a `response_read_error`, not a network error, and is never retried.
- A timeout (`code: "timeout"`) is never retried on either endpoint, since it's ambiguous whether the server received/processed the request.
- A `2xx` response with a body that fails to parse as JSON (`code: "invalid_response"`) carries the actual 2xx status the server returned (usually `200`) and is never retried on either endpoint — the request already reached the server and had its side effect (reply generated / message sent and charged); retrying would risk a double-send or burning AI quota for nothing.
- A `2xx` response whose body stream errors mid-read (`code: "response_read_error"`, e.g. the connection resets after headers arrive) is likewise never retried, for the same reason: response headers arriving means the request already reached the server and may have had its side effect, even though the body was never fully read.

## Webhooks

Verify the `x-tokolaku-signature` header (`sha256=<hex>`, HMAC-SHA256 of the **raw** request body) before trusting a webhook payload. Always use the raw, unmodified request body — a re-serialized JSON string will not match the signature.

```python
from tokolaku.webhooks import verify_webhook_signature, construct_event, TokolakuWebhookSignatureError
```

### Flask

```python
import os
from flask import Flask, request, jsonify
from tokolaku.webhooks import construct_event, TokolakuWebhookSignatureError

app = Flask(__name__)


@app.post("/webhooks/tokolaku")
def tokolaku_webhook():
    raw_body = request.get_data()  # raw bytes — do NOT use request.get_json() here
    try:
        result = construct_event(
            raw_body,
            request.headers.get("x-tokolaku-signature"),
            os.environ["TOKOLAKU_WEBHOOK_SECRET"],
        )
    except TokolakuWebhookSignatureError:
        return jsonify({"error": "invalid signature"}), 401

    event = result["event"]
    # ... handle event
    return jsonify({"received": True})
```

### FastAPI

```python
import os
from fastapi import FastAPI, Request, HTTPException
from tokolaku.webhooks import construct_event, TokolakuWebhookSignatureError

app = FastAPI()


@app.post("/webhooks/tokolaku")
async def tokolaku_webhook(request: Request):
    raw_body = await request.body()  # raw bytes — do NOT depend on request.json() here
    try:
        result = construct_event(
            raw_body,
            request.headers.get("x-tokolaku-signature"),
            os.environ["TOKOLAKU_WEBHOOK_SECRET"],
        )
    except TokolakuWebhookSignatureError:
        raise HTTPException(status_code=401, detail="invalid signature")

    event = result["event"]
    # ... handle event
    return {"received": True}
```

## License

MIT

## Docs

Full API reference: [https://tokolaku.id/api-docs](https://tokolaku.id/api-docs)
