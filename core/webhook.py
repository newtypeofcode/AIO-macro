"""Discord webhook delivery.

Nothing here fires on its own: a message is only sent when a Send Webhook
block runs, or when the user presses Test on the Settings screen. The URL is
a secret -- it is never logged in full, only as a masked form.
"""
import json
import os
import time

DISCORD_HOSTS = ("discord.com", "discordapp.com", "ptb.discord.com",
                 "canary.discord.com")

# Cloudflare rejects the default Python user agent outright ("error code:
# 1010"), so a normal browser one is required for the request to arrive.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

MAX_ATTEMPTS = 3
RETRY_CAP_S = 5.0
# Discord's own limit for a plain (non-boosted) upload.
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_CONTENT_CHARS = 2000


def mask(url: str) -> str:
    """A form of the URL that is safe to put in a log."""
    text = str(url or "")
    if len(text) < 24:
        return "(webhook)"
    return text[:34] + "…" + text[-4:]


def validate(url: str) -> dict:
    """{"valid": bool, "reason": str} -- reasons the UI can explain."""
    text = str(url or "").strip()
    if not text:
        return {"valid": False, "reason": "empty"}
    if not text.startswith("https://"):
        return {"valid": False, "reason": "not_https"}

    try:
        from urllib.parse import urlparse
        parsed = urlparse(text)
    except Exception:
        return {"valid": False, "reason": "bad_format"}

    host = (parsed.hostname or "").lower()
    # Exact host match, not endswith: "discord.com.evil.tld" must not pass.
    if host not in DISCORD_HOSTS:
        return {"valid": False, "reason": "not_discord"}

    # .../api/webhooks/<id>/<token>, read from the END so both that and the
    # versioned .../api/v10/webhooks/<id>/<token> form are accepted.
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 4 or parts[-3] != "webhooks" or "api" not in parts[:-3]:
        return {"valid": False, "reason": "bad_format"}
    if not parts[-2].isdigit() or len(parts[-1]) < 8:
        return {"valid": False, "reason": "bad_format"}
    return {"valid": True, "reason": "ok"}


def _retry_after(response) -> float:
    """How long Discord asked us to wait, in seconds."""
    delay = None
    try:
        body = response.json()
        if isinstance(body, dict) and "retry_after" in body:
            delay = float(body["retry_after"])
    except Exception:
        delay = None
    if delay is None:
        try:
            delay = float(response.headers.get("Retry-After", "1"))
        except (TypeError, ValueError):
            delay = 1.0
    return min(RETRY_CAP_S, max(0.0, delay) + 0.25)


def send(url: str, content: str = "", image_bytes: bytes = None,
         filename: str = "capture.png", username: str = "") -> dict:
    """Post a message, optionally with one PNG attached.

    Returns {"ok": bool, "reason": str}. Never raises: a failed webhook must
    not take the macro down with it.
    """
    check = validate(url)
    if not check["valid"]:
        return {"ok": False, "reason": check["reason"]}

    try:
        import requests
    except ImportError:
        return {"ok": False, "reason": "requests_missing"}

    text = str(content or "")
    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS - 1] + "…"

    payload = {"content": text}
    if username:
        payload["username"] = str(username)[:80]

    if image_bytes is not None and len(image_bytes) > MAX_ATTACHMENT_BYTES:
        return {"ok": False, "reason": "attachment_too_large"}
    if not text and image_bytes is None:
        return {"ok": False, "reason": "nothing_to_send"}

    headers = {"User-Agent": USER_AGENT}
    last = "unknown"
    for attempt in range(MAX_ATTEMPTS):
        try:
            if image_bytes is None:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
            else:
                response = requests.post(
                    url,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": (filename, image_bytes, "image/png")},
                    headers=headers, timeout=30)
        except Exception as exc:
            last = type(exc).__name__
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(1.0)
                continue
            return {"ok": False, "reason": last}

        if 200 <= response.status_code < 300:
            return {"ok": True, "reason": "ok", "status": response.status_code}
        if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
            time.sleep(_retry_after(response))
            continue
        if response.status_code in (401, 403, 404):
            # A wrong or revoked URL will never succeed; retrying is noise.
            return {"ok": False, "reason": "rejected_%d" % response.status_code}
        last = "http_%d" % response.status_code
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(1.0)

    return {"ok": False, "reason": last}


def encode_png(frame_bgr) -> bytes:
    """BGR ndarray -> PNG bytes, or None."""
    if frame_bgr is None:
        return None
    try:
        import cv2
        ok, buf = cv2.imencode(".png", frame_bgr)
        return buf.tobytes() if ok else None
    except Exception:
        return None


def shrink_to_limit(frame_bgr, limit: int = MAX_ATTACHMENT_BYTES):
    """PNG bytes that fit Discord's upload limit.

    A 4K screenshot easily exceeds 8 MB, and Discord rejects the whole
    request rather than truncating -- so the image is halved until it fits
    instead of the send simply failing.
    """
    import cv2

    data = encode_png(frame_bgr)
    if data is None or len(data) <= limit:
        return data

    frame = frame_bgr
    # Halving, and looping until it genuinely fits rather than for a fixed
    # number of tries: a noisy screenshot barely compresses, so a few gentle
    # steps were not enough and the send failed anyway.
    for _ in range(8):
        height, width = frame.shape[:2]
        if width <= 64 or height <= 64:
            break
        frame = cv2.resize(frame, (max(32, width // 2), max(32, height // 2)),
                           interpolation=cv2.INTER_AREA)
        data = encode_png(frame)
        if data is not None and len(data) <= limit:
            return data
    return data
