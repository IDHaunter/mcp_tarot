"""Client clarification flow resolves cards from the local sequence."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from client.bot import TarotBot
from client.config import AppConfig


def test_draw_clarification_resolves_card_from_local_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot looks up position in _sequence and passes TarotCardInput shape."""
    captured: dict[str, object] = {}

    async def _capture_additional(
        card: dict[str, str | bool],
        already_drawn: list[dict[str, str | bool]],
    ) -> dict[str, object]:
        captured["card"] = dict(card)
        captured["already_drawn"] = [dict(item) for item in already_drawn]
        return {
            "card": {
                "id": "c05",
                "reversed": True,
                "name": "Five of Cups",
                "meaning_for_today": "",
                "card_advice": "",
                "orientation": "reversed",
                "meanings": {},
            },
            "influences": [],
        }

    mcp = MagicMock()
    mcp.get_additional_card = AsyncMock(side_effect=_capture_additional)
    llm = MagicMock()
    bot = TarotBot(AppConfig(), mcp, llm)
    bot._sequence = {
        "1": {"id": "01", "reversed": False},
        "2": {"id": "c05", "reversed": True},
    }
    bot._drawn = [{"id": "01", "reversed": False}]
    bot._ask_llm = AsyncMock(return_value="ok")  # type: ignore[method-assign]
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    asyncio.run(bot._draw_clarification("2"))

    mcp.get_additional_card.assert_awaited_once()
    assert captured["card"] == {"id": "c05", "reversed": True}
    assert captured["already_drawn"] == [{"id": "01", "reversed": False}]
    assert bot._drawn == [
        {"id": "01", "reversed": False},
        {"id": "c05", "reversed": True},
    ]
