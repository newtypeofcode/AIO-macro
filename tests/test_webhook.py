"""Discord webhook: URL validation, masking, and the send contract.

Nothing here talks to the network -- `requests.post` is stubbed. What is
verified is that a wrong URL is refused before any request is built, that a
secret never leaks in a readable form, and that nothing is ever sent unless
the user switched it on.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, webhook
from core import settings as smod


GOOD = "https://discord.com/api/webhooks/123456789012345678/AbCdEfGhIjKlMnOpQrStUvWx"


# ----------------------------------------------------------- validation

@pytest.mark.parametrize("url", [
    GOOD,
    "https://discordapp.com/api/webhooks/1234567890/tokentokentoken",
    "https://ptb.discord.com/api/webhooks/1234567890/tokentokentoken",
    "https://discord.com/api/v10/webhooks/1234567890/tokentokentoken",
    GOOD + "/",
])
def test_real_webhook_urls_are_accepted(url):
    assert webhook.validate(url)["valid"] is True, url


@pytest.mark.parametrize("url,reason", [
    ("", "empty"),
    (None, "empty"),
    ("   ", "empty"),
    ("http://discord.com/api/webhooks/1234567890/token123456", "not_https"),
    ("https://example.com/api/webhooks/1234567890/token123456", "not_discord"),
    ("https://discord.com/api/webhooks/notanumber/token123456", "bad_format"),
    ("https://discord.com/api/webhooks/1234567890", "bad_format"),
    ("https://discord.com/nothing/here", "bad_format"),
    ("https://discord.com/api/webhooks/1234567890/short", "bad_format"),
])
def test_bad_urls_are_refused_with_a_reason(url, reason):
    result = webhook.validate(url)
    assert result["valid"] is False
    assert result["reason"] == reason, (url, result)


def test_a_lookalike_host_is_not_discord():
    """endswith() matching would let discord.com.evil.tld through."""
    for host in ("discord.com.evil.tld", "notdiscord.com", "evil-discord.com"):
        url = "https://%s/api/webhooks/1234567890/tokentokentoken" % host
        assert webhook.validate(url)["reason"] == "not_discord", host


# -------------------------------------------------------------- masking

def test_the_url_is_never_returned_in_full():
    masked = webhook.mask(GOOD)
    assert masked != GOOD
    assert GOOD.split("/")[-1] not in masked, "the token must not survive masking"
    assert len(masked) < len(GOOD)


def test_masking_a_short_or_empty_url_reveals_nothing():
    assert webhook.mask("") == "(webhook)"
    assert webhook.mask("https://x") == "(webhook)"


def test_the_api_never_hands_the_url_to_the_frontend(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    smod.save({"webhook_url": GOOD, "webhook_enabled": True})
    api = main.Api()
    payload = api.get_webhook_settings()
    assert GOOD not in repr(payload)
    assert payload["configured"] is True
    assert payload["enabled"] is True


# ---------------------------------------------------------------- sending

class FakeResponse:
    def __init__(self, status=204, body=None, headers=None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


def stub_requests(monkeypatch, responses):
    """Feed `send` a scripted sequence of responses; record the calls."""
    calls = []
    queue = list(responses)

    class FakeRequests:
        @staticmethod
        def post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return queue.pop(0) if queue else FakeResponse()

    import types
    module = types.ModuleType("requests")
    module.post = FakeRequests.post
    monkeypatch.setitem(sys.modules, "requests", module)
    return calls


def test_a_bad_url_is_refused_before_any_request(monkeypatch):
    calls = stub_requests(monkeypatch, [])
    result = webhook.send("https://example.com/nope", "hi")
    assert result["ok"] is False
    assert calls == [], "no request may be built for an invalid URL"


def test_a_plain_message_is_posted_as_json(monkeypatch):
    calls = stub_requests(monkeypatch, [FakeResponse(204)])
    assert webhook.send(GOOD, "hello")["ok"] is True
    assert calls[0]["json"]["content"] == "hello"
    assert "files" not in calls[0]


def test_an_image_is_posted_as_multipart(monkeypatch):
    calls = stub_requests(monkeypatch, [FakeResponse(200)])
    assert webhook.send(GOOD, "look", b"\x89PNG fake")["ok"] is True
    assert "files" in calls[0]
    assert calls[0]["files"]["file"][0] == "capture.png"


def test_sending_nothing_at_all_is_refused(monkeypatch):
    stub_requests(monkeypatch, [FakeResponse(204)])
    assert webhook.send(GOOD, "", None)["reason"] == "nothing_to_send"


def test_an_oversized_attachment_is_refused_rather_than_posted(monkeypatch):
    calls = stub_requests(monkeypatch, [FakeResponse(204)])
    big = b"x" * (webhook.MAX_ATTACHMENT_BYTES + 1)
    assert webhook.send(GOOD, "hi", big)["reason"] == "attachment_too_large"
    assert calls == []


def test_a_long_message_is_truncated_not_rejected(monkeypatch):
    calls = stub_requests(monkeypatch, [FakeResponse(204)])
    webhook.send(GOOD, "x" * 5000)
    assert len(calls[0]["json"]["content"]) <= webhook.MAX_CONTENT_CHARS


def test_rate_limiting_is_retried(monkeypatch):
    calls = stub_requests(monkeypatch, [
        FakeResponse(429, {"retry_after": 0.01}), FakeResponse(204)])
    assert webhook.send(GOOD, "hi")["ok"] is True
    assert len(calls) == 2


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_revoked_url_is_not_retried(monkeypatch, status):
    calls = stub_requests(monkeypatch, [FakeResponse(status)] * 3)
    result = webhook.send(GOOD, "hi")
    assert result["ok"] is False
    assert len(calls) == 1, "retrying a dead webhook is pure noise"


def test_a_network_error_never_raises(monkeypatch):
    import types
    module = types.ModuleType("requests")

    def boom(*_a, **_k):
        raise OSError("no route to host")

    module.post = boom
    monkeypatch.setitem(sys.modules, "requests", module)
    result = webhook.send(GOOD, "hi")
    assert result["ok"] is False
    assert "OSError" in result["reason"]


# ----------------------------------------------------------- attachments

def test_a_frame_encodes_to_png():
    frame = np.full((40, 60, 3), 120, dtype=np.uint8)
    data = webhook.encode_png(frame)
    assert data and data[:4] == b"\x89PNG"


def test_encoding_nothing_returns_nothing():
    assert webhook.encode_png(None) is None


def test_a_large_frame_is_shrunk_to_fit_the_upload_limit():
    rng = np.random.default_rng(0)
    # Noise: incompressible, so the PNG is genuinely large.
    frame = rng.integers(0, 255, (1400, 1400, 3), dtype=np.uint8)
    data = webhook.shrink_to_limit(frame, limit=120_000)
    assert data is not None
    assert len(data) <= 120_000, len(data)


def test_a_small_frame_is_left_alone():
    frame = np.full((20, 20, 3), 200, dtype=np.uint8)
    assert webhook.shrink_to_limit(frame) == webhook.encode_png(frame)


# --------------------------------------------------------------- the block

def test_the_block_exists_and_has_a_handler():
    from core.runner import MacroRunner
    assert "send_webhook" in blocks.BY_TYPE
    assert hasattr(MacroRunner, "_do_send_webhook")


def test_the_block_carries_no_url():
    """The URL lives in Settings so an exported macro can be shared."""
    keys = {f["key"] for f in blocks.BY_TYPE["send_webhook"]["fields"]}
    assert "url" not in keys and "webhook" not in keys


def test_every_attachment_source_is_offered():
    field = [f for f in blocks.BY_TYPE["send_webhook"]["fields"]
             if f["key"] == "source"][0]
    assert field["options"] == ["none", "target window", "whole screen",
                                "region", "saved image"]


def test_nothing_is_sent_while_the_webhook_is_switched_off(tmp_path, monkeypatch):
    import time
    from core.runner import MacroRunner
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    smod.save({"webhook_url": GOOD, "webhook_enabled": False})
    calls = stub_requests(monkeypatch, [FakeResponse(204)])

    lines = []
    runner = MacroRunner(log=lines.append, set_status=lambda **k: None)
    runner.start({"phases": {"setup": [
        blocks.make_block("send_webhook", "w", {"message": "hi"})], "loop": []}},
        hwnd=0, coord_space="screen", loop_forever=False, loop_count=1)
    deadline = time.time() + 10
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)

    assert calls == [], "a disabled webhook must not send"
    assert any("switched off" in line for line in lines)


def test_the_default_is_off_and_empty():
    assert smod.DEFAULTS["webhook_enabled"] is False
    assert smod.DEFAULTS["webhook_url"] == ""
