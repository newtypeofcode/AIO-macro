"""Runtime messages, keyed by the English source string.

Everything the runner and the API write to the log goes through `tr()`. The
key IS the English text, so a missing or mistyped entry degrades to English
rather than to a blank line or a KeyError -- these messages matter most when
something has already gone wrong, and a crash inside the logging path would
hide the failure it was reporting.

Format arguments stay OUTSIDE the translation:

    self._log(tr("Reached %d loop pass(es).") % passes)

so a translation can reorder words but cannot change what is substituted.
`check()` enforces that every entry keeps the same placeholders as its key;
tests/test_messages.py fails the build if one drifts.
"""
import re

from core import messages_ru

DEFAULT_LANGUAGE = "en"
# English is the source text, so it needs no table of its own.
TABLES = {"ru": messages_ru.MESSAGES}
LANGUAGES = ("en",) + tuple(sorted(TABLES))

_language = DEFAULT_LANGUAGE

# %s %d %.1f %5.2f %% and {}, {0}, {name}
_PLACEHOLDER = re.compile(r"%(?:\([^)]*\))?[-+ #0]*[\d*]*(?:\.[\d*]+)?[hlL]?[a-zA-Z%]"
                          r"|\{[^{}]*\}")


def set_language(language: str) -> str:
    global _language
    _language = language if language in LANGUAGES else DEFAULT_LANGUAGE
    return _language


def get_language() -> str:
    return _language


def tr(message: str) -> str:
    """The message in the current language, or the message itself."""
    table = TABLES.get(_language)
    if not table:
        return message
    return table.get(message) or message


def placeholders(text: str) -> list:
    """The format specifiers in `text`, in order.

    Order matters: "%s took %d" and "%d took %s" have the same multiset but
    swapping them silently formats the wrong value into the wrong slot.
    """
    return _PLACEHOLDER.findall(text or "")


def check(language: str) -> list:
    """Entries whose placeholders do not match their key. Empty means safe."""
    table = TABLES.get(language) or {}
    bad = []
    for source, translated in table.items():
        if placeholders(source) != placeholders(translated):
            bad.append(source)
    return bad
