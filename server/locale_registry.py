"""Locale manifest and resolution for tarot card data."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
LOCALES_MANIFEST_PATH = DATA_DIR / "locales.json"
LOCALES_ROOT = DATA_DIR / "locales"


class LocaleError(ValueError):
    """Raised when locale configuration or data is invalid."""


@lru_cache(maxsize=1)
def load_locales_manifest() -> dict[str, Any]:
    """Load ``server/data/locales.json``."""
    if not LOCALES_MANIFEST_PATH.is_file():
        raise LocaleError(f"Locales manifest not found: {LOCALES_MANIFEST_PATH}")
    with LOCALES_MANIFEST_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise LocaleError("locales.json must be a JSON object")
    return data


def available_locale_codes() -> list[str]:
    """Return supported locale codes from the manifest."""
    manifest = load_locales_manifest()
    available = manifest.get("available", [])
    codes: list[str] = []
    if isinstance(available, list):
        for entry in available:
            if isinstance(entry, dict) and entry.get("code"):
                codes.append(str(entry["code"]))
    return codes


def default_locale_code() -> str:
    """Return default locale code from manifest."""
    manifest = load_locales_manifest()
    code = manifest.get("default")
    if not isinstance(code, str) or not code:
        raise LocaleError("locales.json must define a non-empty 'default' locale")
    return code


def resolve_locale(requested: str | None = None) -> str:
    """Resolve active locale from env, argument, or manifest default."""
    if requested:
        code = requested.strip()
    else:
        code = os.environ.get("TAROT_LOCALE", "").strip() or default_locale_code()

    if code not in available_locale_codes():
        allowed = ", ".join(available_locale_codes())
        raise LocaleError(f"Unknown locale {code!r}. Available: {allowed}")

    locale_dir = LOCALES_ROOT / code
    if not locale_dir.is_dir():
        raise LocaleError(f"Locale data directory not found: {locale_dir}")

    return code


def locale_cards_root(locale: str | None = None) -> Path:
    """Return path to card JSON tree for the given locale."""
    code = resolve_locale(locale)
    return LOCALES_ROOT / code
