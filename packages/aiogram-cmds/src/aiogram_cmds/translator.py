"""
Translator protocol and adapters for i18n integration.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol, cast


class Translator(Protocol):
    """Protocol for translation functions.

    Contract:
    - Returns None when translation is missing (allows callers to fallback)
    - Supports optional explicit locale switching via keyword-only ``locale``
    - Supports optional pluralization via ``plural`` and ``count``
    """

    def __call__(
        self,
        key: str,
        *,
        locale: str | None = None,
        plural: str | None = None,
        count: int | None = None,
    ) -> str | None: ...


class I18nAdapter(Protocol):
    """Structural i18n surface; applications need not install an i18n extra."""

    def gettext(self, key: str, /) -> str: ...


def build_translator_from_i18n(i18n_obj: I18nAdapter) -> Translator:
    """
    Build translator adapter from an aiogram ``I18n`` instance.

    Implementation details:
    - aiogram resolves locale from context/middleware; this adapter optionally accepts
      an explicit ``locale`` and uses ``I18n.use_locale(locale)`` when provided.
    - Pluralization maps to aiogram ``gettext`` or application ``ngettext``.
    - Missing translations return None so callers can apply sensible fallbacks.
    """

    def _translate(
        key: str,
        *,
        locale: str | None = None,
        plural: str | None = None,
        count: int | None = None,
    ) -> str | None:
        try:
            # Enter locale context if explicitly provided; otherwise rely on ambient context
            locale_context = getattr(i18n_obj, "with_locale", None) or getattr(
                i18n_obj, "use_locale", None
            )
            ctx = (
                cast(Callable[[str], AbstractContextManager[object]], locale_context)(
                    locale
                )
                if locale
                else nullcontext()
            )
            with ctx:
                if plural is not None and count is not None:
                    # aiogram I18n uses gettext(singular, plural, n); some
                    # application adapters expose GNU-style ngettext instead.
                    plural_gettext = getattr(i18n_obj, "ngettext", None)
                    method = (
                        plural_gettext if callable(plural_gettext) else i18n_obj.gettext
                    )
                    value = cast(Callable[[str, str, int], str], method)(
                        key, plural, count
                    )
                else:
                    value = i18n_obj.gettext(key)
            if not value or value == key:
                return None
            return value
        except Exception:
            return None

    return _translate


def noop_translator(
    key: str,
    *,
    locale: str | None = None,
    plural: str | None = None,
    count: int | None = None,
) -> str | None:
    """No-op translator that always returns None."""
    return None
