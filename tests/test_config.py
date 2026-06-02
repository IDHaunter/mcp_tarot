"""Tests for client.config locale loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from client.config import load_config
from server.locale_registry import LocaleError, default_locale_code


def test_load_config_uses_manifest_default() -> None:
    root = Path(__file__).resolve().parent.parent
    config, locale = load_config(root / "config" / "client.yaml", project_root=root)
    assert locale == default_locale_code()
    assert config.llm.reading_prompt
    assert "{question}" in config.llm.reading_prompt


def test_load_config_russian_locale() -> None:
    root = Path(__file__).resolve().parent.parent
    config, locale = load_config(
        root / "config" / "client.yaml",
        project_root=root,
        locale="ru",
    )
    assert locale == "ru"
    assert "Вопрос пользователя" in config.llm.reading_prompt
    assert config.format.card_label == "Карта"
    assert "нет" in config.bot.skip_commands


def test_load_config_unknown_locale_raises() -> None:
    root = Path(__file__).resolve().parent.parent
    with pytest.raises(LocaleError):
        load_config(
            root / "config" / "client.yaml",
            project_root=root,
            locale="xx",
        )
