"""Isolation every test gets whether it asks for it or not.

Two pieces of process-wide state made the suite depend on the machine it ran
on and on the order it ran in.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, i18n
from core import settings as smod


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read the developer's real settings.json.

    Api() loads settings in its constructor and acts on them, so a test that
    built one picked up whatever the person running the suite had configured.
    Once the language setting existed that stopped being harmless: with
    "language": "ru" saved -- exactly the state after picking Russian in the
    app -- constructing an Api switched the whole process to Russian, and
    every later test that asserted on English log text failed.
    """
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))


@pytest.fixture(autouse=True)
def restore_languages():
    """Put both language singletons back.

    The catalog and the message table are module-level and rewritten in
    place, so a test that switches language leaks into everything that runs
    after it -- and pytest's ordering makes that a failure in a different
    file than the one that caused it.
    """
    catalog_before = blocks.get_language()
    messages_before = i18n.get_language()
    yield
    blocks.set_language(catalog_before)
    i18n.set_language(messages_before)
