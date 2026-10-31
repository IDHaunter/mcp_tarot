"""Tests for MCP tool wiring, schemas, validation, and error handling."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from server.app import mcp
from server.card_store import build_card_payload, load_card_data
from server.models import TarotCardInput


def _call(name: str, arguments: dict[str, Any]) -> Any:
    """Invoke a registered MCP tool and return its content payload."""
    return asyncio.run(mcp.call_tool(name, arguments))


def _text_payload(result: Any) -> dict[str, Any]:
    """Parse the JSON text block from a successful FastMCP tool result."""
    if isinstance(result, tuple):
        content = result[0]
    else:
        content = result
    text = content[0].text
    return json.loads(text)


def test_tool_names_unchanged() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "generate_tarot_sequence",
        "get_card_information",
        "get_additional_card",
    }


def test_tool_schemas_expose_meaningful_descriptions() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    gen = tools["generate_tarot_sequence"]
    assert gen.description
    assert "78" in gen.description
    assert "beginning" in gen.description.lower() or "once" in gen.description.lower()
    assert "not" in gen.description.lower()

    info = tools["get_card_information"]
    assert info.description
    assert "pair" in info.description.lower()
    schema = info.inputSchema
    assert "cards" in schema["properties"]
    card_def = schema["$defs"]["TarotCardInput"]
    assert card_def["properties"]["id"]["description"]
    assert card_def["properties"]["reversed"]["type"] == "boolean"
    assert card_def.get("additionalProperties") is False

    extra = tools["get_additional_card"]
    assert extra.description
    assert "additional" in extra.description.lower() or "follow" in extra.description.lower()
    props = extra.inputSchema["properties"]
    assert "card" in props
    assert "already_drawn" in props
    assert "position_id" not in props
    assert "sequence" not in props
    assert "TarotCardInput" in extra.inputSchema.get("$defs", {})


def test_generate_tarot_sequence_structure() -> None:
    result = _call("generate_tarot_sequence", {})
    sequence = _text_payload(result)
    assert len(sequence) == 78
    assert set(sequence.keys()) == {str(i) for i in range(1, 79)}
    first = sequence["1"]
    assert set(first.keys()) == {"id", "reversed"}
    assert isinstance(first["id"], str)
    assert isinstance(first["reversed"], bool)


def test_get_card_information_success_preserves_payload() -> None:
    result = _call(
        "get_card_information",
        {
            "cards": [
                {"id": "01", "reversed": False},
                {"id": "c01", "reversed": True},
            ]
        },
    )
    data = _text_payload(result)
    assert "error" not in data
    assert len(data["cards"]) == 2
    assert "pair_dependencies" in data
    assert len(data["pair_dependencies"]) == 1

    upright = data["cards"][0]
    expected = build_card_payload("01", reversed_=False)
    assert upright == expected
    assert upright["meanings"] == load_card_data("01")["upright"]
    assert set(upright.keys()) == {
        "id",
        "reversed",
        "name",
        "meaning_for_today",
        "card_advice",
        "orientation",
        "meanings",
    }

    reversed_card = data["cards"][1]
    assert reversed_card["orientation"] == "reversed"
    assert reversed_card["meanings"] == load_card_data("c01")["reversed"]
    assert reversed_card["meanings"] != load_card_data("c01")["upright"]
    # Complete orientation object is preserved (not reduced to advice fields only).
    assert "short" in reversed_card["meanings"]
    assert "general" in reversed_card["meanings"]


def test_get_card_information_empty_list_is_mcp_error() -> None:
    with pytest.raises(ToolError, match="at least 1"):
        _call("get_card_information", {"cards": []})


def test_get_card_information_more_than_78_rejected() -> None:
    cards = [{"id": "01"} for _ in range(79)]
    with pytest.raises(ToolError):
        _call("get_card_information", {"cards": cards})


def test_get_card_information_duplicate_ids_rejected() -> None:
    with pytest.raises(ToolError, match="Duplicate card id"):
        _call(
            "get_card_information",
            {
                "cards": [
                    {"id": "01", "reversed": False},
                    {"id": "01", "reversed": True},
                ]
            },
        )


def test_get_card_information_string_false_rejected() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_card_information",
            {"cards": [{"id": "01", "reversed": "false"}]},
        )


def test_get_card_information_integer_reversed_rejected() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_card_information",
            {"cards": [{"id": "01", "reversed": 0}]},
        )


def test_get_card_information_invalid_id_is_mcp_error_not_error_payload() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_card_information",
            {"cards": [{"id": "99"}]},
        )


def test_get_additional_card_success() -> None:
    result = _call(
        "get_additional_card",
        {
            "card": {"id": "c05", "reversed": True},
            "already_drawn": [{"id": "01", "reversed": False}],
        },
    )
    data = _text_payload(result)
    assert "error" not in data
    assert "position_id" not in data
    assert data["card"] == build_card_payload("c05", reversed_=True)
    assert isinstance(data["influences"], list)
    assert data["influences"]


def test_get_additional_card_already_drawn_duplicate_ids_rejected() -> None:
    with pytest.raises(ToolError, match="Duplicate card id"):
        _call(
            "get_additional_card",
            {
                "card": {"id": "01", "reversed": False},
                "already_drawn": [
                    {"id": "c01"},
                    {"id": "c01"},
                ],
            },
        )


def test_get_additional_card_rejects_already_selected_card() -> None:
    with pytest.raises(ToolError, match="already drawn"):
        _call(
            "get_additional_card",
            {
                "card": {"id": "01", "reversed": False},
                "already_drawn": [{"id": "01", "reversed": False}],
            },
        )


def test_get_additional_card_malformed_card_rejected() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_additional_card",
            {
                "card": {"id": "01", "reversed": "false"},
                "already_drawn": [],
            },
        )


def test_get_additional_card_invalid_card_id_rejected() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_additional_card",
            {
                "card": {"id": "99", "reversed": False},
                "already_drawn": [],
            },
        )


def test_get_additional_card_invalid_already_drawn_entry_rejected() -> None:
    with pytest.raises(ToolError):
        _call(
            "get_additional_card",
            {
                "card": {"id": "c05", "reversed": True},
                "already_drawn": [{"id": "01", "name": "extra"}],
            },
        )


def test_tarot_card_input_usable_in_direct_tool_path() -> None:
    """Models convert cleanly for relation helpers / payload building."""
    card = TarotCardInput(id="01")
    payload = build_card_payload(card.id, card.reversed)
    assert payload["orientation"] == "upright"
