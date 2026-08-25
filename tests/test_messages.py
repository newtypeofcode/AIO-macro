"""The runtime message table.

These lines are read while something is already going wrong, so the failure
modes worth guarding are the silent ones: a dropped %s formats the wrong
value into the log, a missing entry must degrade to English rather than to a
blank line, and an entry nobody logs is a translation nobody ever sees.
"""
import ast
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import i18n, messages_ru

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def restore_language():
    before = i18n.get_language()
    yield
    i18n.set_language(before)


def _tr_literals(path):
    """Every literal handed to tr() in one file.

    Read from the syntax tree, not by regex: half of these calls are split
    across lines, and only the parser puts the pieces back together.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            found.append(node.args[0].value)
    return found


def logged_messages():
    """Every message the app actually writes to the log.

    tests/ and tools/ are deliberately not scanned: a string wrapped only by
    a test would make the table look complete while the app logged English.
    """
    paths = [os.path.join(ROOT, "main.py")]
    core = os.path.join(ROOT, "core")
    paths += [os.path.join(core, name) for name in sorted(os.listdir(core))
              if name.endswith(".py")]
    messages = set()
    for path in paths:
        messages.update(_tr_literals(path))
    return messages


def test_the_scan_finds_the_messages_it_is_checking_against():
    """Both directions below compare against this scan, so a scan that
    quietly stopped finding anything would pass them without checking."""
    found = logged_messages()
    assert "Run finished." in found
    # Split across two source lines, so a regex-based scan would miss it.
    assert "Target window disappeared -- stopping so clicks cannot " \
           "land on whatever is behind it." in found


def test_every_logged_message_has_a_russian_entry():
    """New messages arrive in English; this is what stops them staying that
    way in Russian mode."""
    missing = sorted(logged_messages() - set(messages_ru.MESSAGES))
    assert not missing, missing


def test_the_table_has_no_entry_nobody_logs():
    stale = sorted(set(messages_ru.MESSAGES) - logged_messages())
    assert not stale, stale


def test_every_translation_keeps_the_placeholders_of_its_key():
    for language in i18n.TABLES:
        assert i18n.check(language) == [], language


def test_check_catches_a_dropped_placeholder(monkeypatch):
    """The guard has to actually catch something, or it is decoration."""
    monkeypatch.setitem(i18n.TABLES, "ru", {"Target: %s": "Цель"})
    assert i18n.check("ru") == ["Target: %s"]


def test_check_catches_placeholders_that_changed_order(monkeypatch):
    """Same specifiers, swapped: nothing raises, the values simply land in
    each other's slots."""
    monkeypatch.setitem(i18n.TABLES, "ru",
                        {"Picked %d, %s": "%s, %d"})
    assert i18n.check("ru") == ["Picked %d, %s"]


def test_a_missing_translation_keeps_the_english_text():
    i18n.set_language("ru")
    assert i18n.tr("Nothing translates this.") == "Nothing translates this."


def test_an_empty_translation_keeps_the_english_text(monkeypatch):
    monkeypatch.setitem(i18n.TABLES, "ru", {"Run finished.": ""})
    i18n.set_language("ru")
    assert i18n.tr("Run finished.") == "Run finished."


def test_switching_language_changes_what_tr_returns():
    i18n.set_language("en")
    assert i18n.tr("Run finished.") == "Run finished."
    i18n.set_language("ru")
    assert i18n.tr("Run finished.") == "Прогон завершён."


def test_switching_back_restores_the_english():
    i18n.set_language("ru")
    i18n.set_language("en")
    assert i18n.tr("Run finished.") == "Run finished."


def test_an_unsupported_language_falls_back_instead_of_blanking():
    assert i18n.set_language("klingon") == i18n.DEFAULT_LANGUAGE
    assert i18n.tr("Run finished.") == "Run finished."


def test_indented_messages_keep_their_indent():
    """The log panel reads those leading spaces as structure -- a fallback
    line that loses them stops looking like a nested step."""
    for source, translated in messages_ru.MESSAGES.items():
        indent = len(source) - len(source.lstrip(" "))
        assert len(translated) - len(translated.lstrip(" ")) == indent, source


def test_every_entry_is_actually_russian():
    for source, translated in messages_ru.MESSAGES.items():
        assert re.search(r"[а-яА-Я]", translated), source


def test_no_entry_carries_markdown():
    """Log lines are rendered as plain text, so `**bold**` reaches the user
    as literal asterisks."""
    for source, translated in messages_ru.MESSAGES.items():
        assert "**" not in translated, source
