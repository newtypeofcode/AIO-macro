"""Bilingual block help.

The catalog is a module-level singleton every consumer holds a reference to,
so switching language rewrites it in place. These tests guard the two halves
staying in sync and the switch actually taking effect both ways.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import block_help, blocks


@pytest.fixture(autouse=True)
def restore_language():
    before = blocks.get_language()
    yield
    blocks.set_language(before)


def test_both_languages_are_complete():
    """A half-finished translation shows up here rather than as blank
    tooltips in the app."""
    for language in block_help.LANGUAGES:
        assert block_help.missing(language) == [], language


def test_every_block_has_a_description_in_both_languages():
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        for spec in blocks.catalog():
            assert spec["desc"].strip(), (spec["type"], language)


def test_every_field_has_help_in_both_languages():
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        for spec in blocks.catalog():
            for field in spec["fields"]:
                if field["key"] == "region":
                    continue
                assert field["help"].strip(), (spec["type"], field["key"], language)


def test_switching_actually_changes_the_text():
    blocks.set_language("en")
    english = {s["type"]: s["desc"] for s in blocks.catalog()}
    blocks.set_language("ru")
    russian = {s["type"]: s["desc"] for s in blocks.catalog()}
    assert english != russian
    # Not just one entry: every block must be translated.
    same = [t for t in english if english[t] == russian[t]]
    assert not same, same


def test_switching_back_restores_the_first_language():
    blocks.set_language("en")
    first = {s["type"]: s["desc"] for s in blocks.catalog()}
    blocks.set_language("ru")
    blocks.set_language("en")
    assert {s["type"]: s["desc"] for s in blocks.catalog()} == first


def test_russian_help_is_actually_russian():
    import re
    blocks.set_language("ru")
    for spec in blocks.catalog():
        assert re.search(r"[а-яА-Я]", spec["desc"]), spec["type"]


def test_english_help_is_english_outside_its_examples():
    """Cyrillic belongs in the English text only as a quoted example -- the
    Latin/Cyrillic C that OCR confuses, the key that types ф on a Russian
    layout, the string Type Text proves it can type. Prose in Russian means
    an entry was never translated."""
    import re
    blocks.set_language("en")
    quoted = re.compile(r"[\"'`«][^\"'`»]*[\"'`»]")
    for spec in blocks.catalog():
        for label, blob in [("desc", spec["desc"])] + \
                [(f["key"], f["help"]) for f in spec["fields"]]:
            prose = quoted.sub("", blob)
            # A lone Cyrillic letter is a specimen being pointed at ("a Latin
            # C with a Cyrillic С"); two or more in a row is a word.
            stray = re.findall(r"[а-яА-Я]{2,}", prose)
            assert not stray, (spec["type"], label, stray)


def test_help_text_carries_no_markdown():
    """Tooltips are set with textContent, so `**bold**` reaches the user as
    literal asterisks."""
    import re
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        for spec in blocks.catalog():
            for label, blob in [("desc", spec["desc"])] + \
                    [(f["key"], f["help"]) for f in spec["fields"]]:
                assert not re.search(r"\*\*|__[a-zA-Zа-яА-Я]", blob), \
                    (language, spec["type"], label)


def test_an_unknown_language_falls_back_rather_than_blanking():
    assert blocks.set_language("klingon") == block_help.DEFAULT_LANGUAGE
    assert all(s["desc"].strip() for s in blocks.catalog())


def test_the_language_setting_exists_and_defaults_to_english():
    from core import settings as smod
    assert smod.DEFAULTS["language"] == "en"


# --------------------------------------------------------- the API wiring

@pytest.fixture
def api(tmp_path, monkeypatch):
    """A real Api against a throwaway settings file."""
    from core import settings as smod
    import main
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    return main, smod


def test_choosing_a_language_switches_the_catalog_not_just_the_setting(api):
    """The catalog is built on the Python side, so persisting the setting is
    only half the job -- without this the UI chrome switched but every block
    description and tooltip stayed in the import-time language."""
    main, smod = api
    instance = main.Api()
    instance.set_setting("language", "ru")
    assert blocks.get_language() == "ru"
    assert smod.load()["language"] == "ru"
    desc = instance.get_bootstrap()["catalog"][0]["desc"]
    import re
    assert re.search(r"[а-яА-Я]", desc), desc

    instance.set_setting("language", "en")
    assert blocks.get_language() == "en"
    assert not re.search(r"[а-яА-Я]{2,}",
                         instance.get_bootstrap()["catalog"][0]["desc"])


def test_the_saved_language_is_applied_before_the_first_bootstrap(api):
    """Startup order matters: get_bootstrap is the first call the UI makes,
    and it must already carry the saved language."""
    main, smod = api
    smod.save({"language": "ru"})
    blocks.set_language("en")
    instance = main.Api()
    assert blocks.get_language() == "ru"
    import re
    assert re.search(r"[а-яА-Я]", instance.get_bootstrap()["catalog"][0]["desc"])


def test_an_unsupported_language_is_not_left_in_the_settings_file(api):
    """Saving the request rather than the result would leave settings.json
    naming a language nothing can render, and the picker highlighting
    nothing."""
    main, smod = api
    instance = main.Api()
    merged = instance.set_setting("language", "klingon")
    assert merged["language"] == block_help.DEFAULT_LANGUAGE
    assert smod.load()["language"] == block_help.DEFAULT_LANGUAGE
    assert blocks.get_language() == block_help.DEFAULT_LANGUAGE


def test_resetting_settings_puts_the_catalog_back_too(api):
    main, smod = api
    instance = main.Api()
    instance.set_setting("language", "ru")
    instance.reset_settings()
    assert blocks.get_language() == smod.DEFAULTS["language"]


def test_setting_something_else_leaves_the_language_alone(api):
    main, _ = api
    instance = main.Api()
    instance.set_setting("language", "ru")
    instance.set_setting("action_delay_ms", 25)
    assert blocks.get_language() == "ru"


def test_the_two_tables_have_identical_keys():
    from core import block_help_en as en
    assert set(en.HELP) == set(block_help.HELP)
    assert set(en.SHARED) == set(block_help.SHARED)
    for block_type, entry in block_help.HELP.items():
        assert set(en.HELP[block_type].get("fields", {})) == set(entry.get("fields", {})), \
            block_type


def test_missing_reports_gaps_when_a_translation_is_incomplete(monkeypatch):
    """The guard has to actually catch something, or it is decoration."""
    from core import block_help_en as en
    trimmed = dict(en.HELP)
    victim = sorted(trimmed)[0]
    trimmed[victim] = {"desc": "", "fields": {}}
    monkeypatch.setattr(en, "HELP", trimmed)
    gaps = block_help.missing("en")
    assert victim in gaps, gaps
