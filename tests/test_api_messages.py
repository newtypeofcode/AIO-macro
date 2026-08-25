"""What the API writes for the user, in the language the user picked.

main.py both logs and hands rows across the bridge, and the frontend renders
those rows as plain text with no table of its own -- so a word left in
English here is English on screen whatever ui/app.js has been taught. What
these guard is the seam: a translated sentence with an untranslated value
substituted into it reads as translated at a glance and is the failure that
survives review.
"""
import os
import re
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CYRILLIC = re.compile(r"[а-яА-Я]")
GOOD_HOOK = ("https://discord.com/api/webhooks/123456789012345678"
             "/AbCdEfGhIjKlMnOpQrStUvWx")


@pytest.fixture
def api():
    """A real Api talking Russian.

    conftest already points settings at a throwaway file and puts both
    language singletons back afterwards.
    """
    import main
    instance = main.Api()
    instance.set_setting("language", "ru")
    return instance


@pytest.fixture
def quiet_machine(monkeypatch):
    """The health check without touching the machine.

    The real one nudges the cursor of whoever is running the suite and grabs
    their screen, and every detail it reports then depends on both.
    """
    from core import capture
    from core import mouse as mousemod

    class StuckMouse:
        def position(self):
            return (0, 0)

        def nudge(self, dx=1, dy=0):
            pass

        def move_to(self, x, y):
            pass

    monkeypatch.setattr(mousemod, "Mouse", StuckMouse)
    monkeypatch.setattr(capture, "capture_target_bgr",
                        lambda *a, **kw: np.zeros((4, 4, 3), dtype=np.uint8))


def last_log(instance):
    return instance._log_history[-1]["msg"]


# ---------------------------------------------------------------- target

def test_attaching_to_the_whole_screen_logs_no_english_noun(api):
    """The sentence was translated and the noun dropped into it was not, so
    Russian users read "Цель выбрана: whole screen"."""
    api.set_target(0)
    assert last_log(api) == "Цель выбрана: весь экран"


def test_a_window_title_is_logged_exactly_as_windows_gave_it(api):
    """Only the words around it translate -- a title is a name, and a
    translated one names a window nobody has."""
    api.set_target(0, "Untitled - Notepad")
    assert last_log(api) == "Цель выбрана: Untitled - Notepad"


def test_the_screen_target_names_itself_in_the_users_language(api):
    """This title is shown as-is in the header and the status bar; the
    frontend only reaches for its own wording when it arrives empty."""
    api.use_screen_target()
    assert api.get_target_info()["title"] == "Весь экран"


# ---------------------------------------------------------------- status

def test_an_idle_run_is_called_idle_in_russian(api):
    assert api.get_status()["action"] == "Простой"


def test_the_word_the_runner_parks_after_a_run_is_translated_too(api):
    """MacroRunner writes the English word straight back into the status
    when a run ends, so translating only the startup value would leave the
    bar in English from the first run onwards."""
    api._set_status(action="Idle")
    assert api.get_status()["action"] == "Простой"


def test_a_phase_name_from_the_runner_is_left_alone(api):
    """The runner translates its own status text before setting it; the
    bridge must not try to translate it a second time."""
    api._set_status(action="Цикл #3 Клик 10,20")
    assert api.get_status()["action"] == "Цикл #3 Клик 10,20"


# --------------------------------------------------------------- webhook

def test_a_delivered_webhook_test_is_reported_in_russian(api, monkeypatch):
    from core import settings as smod, webhook as hook
    smod.update({"webhook_url": GOOD_HOOK})
    monkeypatch.setattr(hook, "send", lambda *a, **kw: {"ok": True})
    api.test_webhook()
    assert last_log(api) == "Тест вебхука: доставлено."


def test_a_failed_webhook_test_still_names_the_machine_code(api, monkeypatch):
    """Deliberate: not_https is the string someone quotes when asking what
    went wrong, and a Russian paraphrase of it helps nobody."""
    from core import settings as smod, webhook as hook
    smod.update({"webhook_url": GOOD_HOOK})
    monkeypatch.setattr(hook, "send",
                        lambda *a, **kw: {"ok": False, "reason": "not_https"})
    api.test_webhook()
    assert last_log(api) == "Тест вебхука: not_https"


def test_the_message_sent_to_discord_is_translated(api, monkeypatch):
    """It is read in Discord rather than in the app, which is exactly why it
    was missed."""
    from core import settings as smod, webhook as hook
    smod.update({"webhook_url": GOOD_HOOK})
    sent = []

    def record(url, text, **kw):
        sent.append(text)
        return {"ok": True}

    monkeypatch.setattr(hook, "send", record)
    api.test_webhook()
    assert CYRILLIC.search(sent[0]), sent


def test_the_webhook_preview_caption_is_translated(api):
    """The caption under the preview is rendered straight from what crosses
    the bridge."""
    assert api.preview_webhook_source("none")["detail"] == "только текст"


# ------------------------------------------------------------ diagnostics

def test_every_health_row_is_named_in_the_users_language(api, quiet_machine):
    rows = api.run_health_check()
    english = [row["name"] for row in rows if not CYRILLIC.search(row["name"])]
    assert not english, english


def test_a_health_row_detail_is_translated_too(api, quiet_machine):
    """The name and the detail come from different literals, so a translated
    name proves nothing about the sentence beside it."""
    details = [row["detail"] for row in api.run_health_check()]
    assert "курсор не сдвинулся" in details, details


def test_a_health_row_with_no_target_says_so_in_russian(api, quiet_machine):
    from core import settings as smod
    smod.update({"target_mode": "window", "target_hwnd": 999999999,
                 "target_title": ""})
    details = [row["detail"] for row in api.run_health_check()]
    assert "не выбрано" in details, details


def test_a_non_standard_display_scale_warns_in_russian(api, quiet_machine,
                                                       monkeypatch):
    """The warning is glued onto the number, so it also has to keep the
    leading space that separates it."""
    import main
    monkeypatch.setattr(main.wm, "get_display_scale_percent", lambda: 125)
    details = [row["detail"] for row in api.run_health_check()]
    assert "125% — координаты могут съезжать" in details, details


def test_the_health_log_line_translates_its_verdict(api, quiet_machine):
    """OK and FAIL are substituted into the sentence, which is how they
    stayed English while the sentence around them was translated."""
    rows = api.run_health_check()
    lines = [entry["msg"] for entry in api._log_history[-len(rows):]]
    assert lines, "the check logged nothing"
    for line in lines:
        assert "OK" not in line and "FAIL" not in line, line


def test_a_broken_ocr_install_is_reported_in_russian(api, monkeypatch):
    from core import ocr

    def boom():
        raise RuntimeError("cv2 is not installed")

    monkeypatch.setattr(ocr, "engine_name", boom)
    assert api.get_bootstrap()["ocr_engine"] == "недоступен"


def test_english_mode_keeps_every_health_row_english(quiet_machine):
    """tr() falls through to its key, so a row that came out Russian here
    would mean the Russian was hardcoded rather than looked up."""
    import main
    instance = main.Api()
    instance.set_setting("language", "en")
    for row in instance.run_health_check():
        assert not CYRILLIC.search(row["name"] + row["detail"]), row
