"""Bilingual block help.

The catalog is a module-level singleton every consumer holds a reference to,
so switching language rewrites it in place. These tests guard the two halves
staying in sync and the switch actually taking effect both ways.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import block_help, blocks, i18n


@pytest.fixture(autouse=True)
def restore_language():
    before = blocks.get_language()
    before_messages = i18n.get_language()
    yield
    blocks.set_language(before)
    i18n.set_language(before_messages)


def label_map():
    """Every label the catalog currently shows, keyed by where it sits."""
    out = {}
    for spec in blocks.catalog():
        out[spec["type"]] = spec["label"]
        for field in spec["fields"]:
            out["%s.%s" % (spec["type"], field["key"])] = field["label"]
    return out


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


def test_every_label_is_filled_in_in_both_languages():
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        for name, text in label_map().items():
            assert text.strip(), (name, language)


def test_no_label_falls_back_to_its_own_identifier():
    """apply_to labels an untranslated field with its key so the row still
    renders, which is exactly how a block added to blocks.py and never added
    to the help tables would sneak into the palette as "wait_image_gone"."""
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        for spec in blocks.catalog():
            assert spec["label"] != spec["type"], (spec["type"], language)
            for field in spec["fields"]:
                assert field["label"] != field["key"], \
                    (spec["type"], field["key"], language)


def test_switching_changes_the_labels_too():
    """The palette chips and the field rows are the most visible half of the
    translation, and they come from a different part of the entry than the
    tooltips."""
    blocks.set_language("en")
    english = label_map()
    blocks.set_language("ru")
    russian = label_map()
    # X and Y are the same symbol in both languages; nothing else may
    # survive the switch untouched.
    untranslated = [name for name, text in english.items()
                    if russian[name] == text and text not in ("X", "Y")]
    assert not untranslated, untranslated


def test_switching_back_restores_the_labels():
    blocks.set_language("en")
    first = label_map()
    blocks.set_language("ru")
    blocks.set_language("en")
    assert label_map() == first


def test_no_russian_label_leaks_into_english_mode():
    import re
    blocks.set_language("en")
    for name, text in label_map().items():
        assert not re.search(r"[а-яА-Я]", text), (name, text)


def test_russian_labels_are_russian_apart_from_the_symbols():
    """X and Y stay X and Y; a Latin word in a Russian label is an entry
    that was copied over rather than translated."""
    import re
    blocks.set_language("ru")
    for name, text in label_map().items():
        assert not re.findall(r"[a-zA-Z]{2,}", text), (name, text)


def test_a_field_key_keeps_one_wording_across_blocks():
    """timeout_ms is "Timeout ms" in all seven blocks that carry it, so it
    has to be one Russian phrase in all seven too. Where the English itself
    distinguishes -- Drag's From X against Click's X -- the Russian is
    allowed to follow it, which is why the English label is part of the
    grouping key."""
    blocks.set_language("en")
    english = label_map()
    blocks.set_language("ru")
    russian = label_map()
    wording = {}
    for spec in blocks.catalog():
        for field in spec["fields"]:
            name = "%s.%s" % (spec["type"], field["key"])
            wording.setdefault((field["key"], english[name]), set()) \
                   .add(russian[name])
    drift = {key: sorted(seen) for key, seen in wording.items()
             if len(seen) > 1}
    assert not drift, drift


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


def run_lines(setup=()):
    """Everything the runner logs for one real run of `setup`."""
    from core.runner import MacroRunner
    lines = []
    runner = MacroRunner(log=lines.append, set_status=lambda **kw: None)
    runner.start({"phases": {"setup": list(setup), "loop": []}}, hwnd=0,
                 coord_space="screen", loop_forever=False, loop_count=1)
    deadline = time.time() + 15.0
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running(), "runner did not finish"
    return lines


def empty_run_lines():
    """What the runner logs for a macro with nothing in it."""
    return run_lines()


def test_choosing_a_language_switches_the_run_log_too(api, monkeypatch):
    """Block help and log lines come from different tables, so the catalog
    switching over proves nothing about what the runner writes."""
    main, _ = api
    monkeypatch.setitem(i18n.TABLES, "ru",
                        {"Run finished.": "Прогон завершён."})
    instance = main.Api()

    instance.set_setting("language", "en")
    assert "Run finished." in empty_run_lines()

    instance.set_setting("language", "ru")
    assert "Прогон завершён." in empty_run_lines()


def test_the_two_tables_have_identical_keys():
    from core import block_help_en as en
    assert set(en.HELP) == set(block_help.HELP)
    assert set(en.SHARED) == set(block_help.SHARED)
    for block_type, entry in block_help.HELP.items():
        assert set(en.HELP[block_type].get("fields", {})) == set(entry.get("fields", {})), \
            block_type


def test_both_tables_carry_a_label_for_every_entry():
    from core import block_help_en as en
    for table in (block_help.HELP, en.HELP):
        for block_type, entry in table.items():
            assert entry.get("label"), block_type
            for key, info in entry.get("fields", {}).items():
                assert info.get("label"), (block_type, key)
    for shared in (block_help.SHARED, en.SHARED):
        for key, info in shared.items():
            assert info.get("label"), key


def test_missing_reports_gaps_when_a_translation_is_incomplete(monkeypatch):
    """The guard has to actually catch something, or it is decoration."""
    from core import block_help_en as en
    trimmed = dict(en.HELP)
    victim = sorted(trimmed)[0]
    trimmed[victim] = {"desc": "", "fields": {}}
    monkeypatch.setattr(en, "HELP", trimmed)
    gaps = block_help.missing("en")
    assert victim in gaps, gaps


def test_missing_counts_an_absent_label_as_a_gap(monkeypatch):
    """A label is as visible as a tooltip and easier to forget, so leaving
    one out has to fail the same way -- and it must be reported even when
    the help beside it is perfectly translated."""
    import copy
    from core import block_help_en as en
    trimmed = copy.deepcopy(en.HELP)
    trimmed["click"]["label"] = ""
    del trimmed["click"]["fields"]["x"]["label"]
    monkeypatch.setattr(en, "HELP", trimmed)
    gaps = block_help.missing("en")
    assert "click.label" in gaps, gaps
    assert "click.x.label" in gaps, gaps
    assert "click.x" not in gaps, gaps


def test_missing_counts_an_absent_shared_label_as_a_gap(monkeypatch):
    import copy
    from core import block_help_en as en
    trimmed = copy.deepcopy(en.SHARED)
    trimmed["on_fail_after"]["label"] = ""
    monkeypatch.setattr(en, "SHARED", trimmed)
    assert "SHARED.on_fail_after.label" in block_help.missing("en")


# ------------------------------------------------------------ the run log

def summary_map():
    """One summary per block type, as the log would print it."""
    return {spec["type"]: blocks.summarise(blocks.make_block(spec["type"], "x"))
            for spec in blocks.catalog()}


def test_the_run_log_summary_translates_like_every_other_log_line():
    """The per-block trace is the highest-volume line in the log, and it used
    to be built from English templates -- so a Russian run log was a wall of
    "Click image 'play'" with a Russian sentence every twenty lines."""
    i18n.set_language("en")
    english = summary_map()
    i18n.set_language("ru")
    russian = summary_map()
    untranslated = [t for t, text in english.items() if russian[t] == text]
    assert not untranslated, untranslated


def test_the_summary_keeps_the_values_the_macro_stored():
    """Only the words around them are translated: an image called 'play' is
    still called 'play' in Russian, or it names a file nobody has."""
    import re
    block = blocks.make_block("click_image", "a", {"template": "play"})
    i18n.set_language("ru")
    summary = blocks.summarise(block)
    assert "play" in summary, summary
    assert re.search(r"[а-яА-Я]", summary), summary


def test_the_phase_headings_follow_the_language():
    """main.py reads PHASE_LABELS when the UI bootstraps and the runner reads
    it on every phase line, both of them long after import -- a plain dict of
    English words would have frozen the language the process started in."""
    import re
    i18n.set_language("en")
    english = [blocks.PHASE_LABELS[key] for key in blocks.PHASES]
    i18n.set_language("ru")
    russian = [blocks.PHASE_LABELS[key] for key in blocks.PHASES]
    assert english == ["Setup", "Loop"]
    assert all(re.search(r"[а-яА-Я]", text) for text in russian), russian


def test_the_phase_keys_are_never_translated():
    """They are identifiers, stored inside every saved macro: translating one
    would make yesterday's macro load with an empty phase."""
    i18n.set_language("ru")
    assert list(blocks.PHASE_LABELS) == list(blocks.PHASES)


def test_no_run_log_line_leaks_a_phase_identifier():
    """"setup" and "loop" are storage keys that happen to read as English
    words; the log has to name the phase the way its column heading does."""
    i18n.set_language("ru")
    lines = run_lines([blocks.make_block("wait_ms", "a", {"ms": 0})])
    leaked = [line for line in lines if "setup" in line or "loop" in line]
    assert not leaked, leaked


def test_a_vision_block_says_in_russian_why_it_gave_up():
    """_fail logs its argument exactly as handed over, so a caller that skips
    tr() leaves the most-read line in the app English."""
    import re
    block = blocks.make_block("wait_image", "a",
                              {"template": "nothing-here", "timeout_ms": 0})
    i18n.set_language("ru")
    reasons = [line for line in run_lines([block]) if "nothing-here" in line]
    assert reasons, "the block logged no reason at all"
    assert re.search(r"[а-яА-Я]", reasons[-1]), reasons


def test_summarise_survives_a_block_the_catalog_has_no_entry_for():
    """Its last resort is the catalog label, and an unknown type has no
    entry to take one from."""
    for language in block_help.LANGUAGES:
        blocks.set_language(language)
        assert blocks.summarise({"type": "no_such_block"}) == "no_such_block"
        assert isinstance(blocks.summarise({}), str)
