"""Pytest fixtures and environment defaults."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _tarot_locale_en(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use English card data unless a test overrides locale."""
    monkeypatch.setenv("TAROT_LOCALE", "en")
