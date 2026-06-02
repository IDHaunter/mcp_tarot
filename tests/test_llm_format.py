"""Tests for client.llm_format."""

from __future__ import annotations

from client.config import FormatConfig
from client.llm_format import (
    build_card_name_index,
    format_card_for_llm,
    format_clarification_for_llm,
    format_pair_relations_for_llm,
    format_reading_info_for_llm,
    resolve_card_display_name,
)

_FMT = FormatConfig()


def _sample_card(*, reversed_: bool = False) -> dict:
    orientation = "reversed" if reversed_ else "upright"
    meanings = {
        "meaning_for_today": "Today text",
        "card_advice": "Advice text",
        "short": "short meaning",
        "general": "general meaning",
        "in_love": "love meaning",
        "in_situation": "situation meaning",
    }
    return {
        "id": "22",
        "reversed": reversed_,
        "name": "The World",
        "meaning_for_today": meanings["meaning_for_today"],
        "card_advice": meanings["card_advice"],
        "orientation": orientation,
        "meanings": meanings,
    }


def test_format_card_embeds_orientation_in_title_only() -> None:
    text = format_card_for_llm(_sample_card(reversed_=True), _FMT, index=1)
    assert "Card 1: The World (reversed)" in text
    assert '"reversed"' not in text
    assert '"orientation"' not in text
    assert "Short meaning: short meaning" in text
    assert "Situation: situation meaning" in text
    assert "Advice: Advice text" in text


def test_format_card_upright_has_no_reversed_suffix() -> None:
    text = format_card_for_llm(_sample_card(reversed_=False), _FMT, index=2)
    assert "Card 2: The World\n" in text or text.startswith("Card 2: The World\n")
    assert "(reversed)" not in text


def test_format_pair_relations_readable() -> None:
    pairs = [
        {
            "card_a": {"id": "22"},
            "card_b": {"id": "05"},
            "from_a_to_b": "Spiritual fulfillment.",
            "from_b_to_a": "Higher wisdom.",
        }
    ]
    names = {"22": "The World", "05": "The Emperor"}
    text = format_pair_relations_for_llm(pairs, names, _FMT)
    assert "Interactions:" in text
    assert "* The World + The Emperor:" in text
    assert "Spiritual fulfillment." in text
    assert "Higher wisdom." in text
    assert '"card_a"' not in text


def test_format_reading_info_preserves_card_order() -> None:
    info = {
        "cards": [
            {**_sample_card(), "id": "01", "name": "The Fool", "reversed": False},
            {**_sample_card(), "id": "02", "name": "The Magician", "reversed": True},
        ],
        "pair_dependencies": [
            {
                "card_a": {"id": "01"},
                "card_b": {"id": "02"},
                "from_a_to_b": "Link A to B",
                "from_b_to_a": None,
            }
        ],
    }
    text = format_reading_info_for_llm(info, _FMT)
    fool_pos = text.index("The Fool")
    magician_pos = text.index("The Magician")
    assert fool_pos < magician_pos
    assert "Link A to B" in text


def test_format_clarification_excludes_position_id() -> None:
    extra = {
        "position_id": "42",
        "card": _sample_card(reversed_=False),
        "influences": [
            {
                "card_a": {"id": "22"},
                "card_b": {"id": "01"},
                "from_a_to_b": "Clarify link",
                "from_b_to_a": None,
            }
        ],
    }
    spread = [{"id": "01", "name": "The Fool", "reversed": False}]
    text = format_clarification_for_llm(extra, _FMT, drawn_cards=spread)
    assert "position_id" not in text
    assert "42" not in text
    assert "Clarification card:" in text
    assert "Clarify link" in text
    assert "* The World + The Fool:" in text


def test_clarification_interactions_use_names_not_major_ids() -> None:
    """Spread slots with only id/reversed must still resolve major arcana names."""
    extra = {
        "card": {
            "id": "c12",
            "name": "Knight of Cups",
            "reversed": False,
            "meanings": {"short": "x"},
            "meaning_for_today": "t",
            "card_advice": "a",
        },
        "influences": [
            {
                "card_a": {"id": "04"},
                "card_b": {"id": "c12"},
                "from_a_to_b": "Stability meets emotion.",
                "from_b_to_a": None,
            }
        ],
    }
    spread_slots = [{"id": "04", "reversed": True}]
    text = format_clarification_for_llm(extra, _FMT, drawn_cards=spread_slots)
    assert "* The Empress + Knight of Cups:" in text
    assert "04 +" not in text
    assert "04 + Knight" not in text


def test_format_card_russian_labels() -> None:
    ru = FormatConfig(
        card_label="Карта",
        reversed_suffix="перевёрнутая",
        label_short="Кратко",
    )
    text = format_card_for_llm(_sample_card(reversed_=True), ru, index=1)
    assert "Карта 1: The World (перевёрнутая)" in text
    assert "Кратко: short meaning" in text


def test_resolve_card_display_name_loads_major_from_data() -> None:
    name = resolve_card_display_name("04", {})
    assert name == "The Empress"


def test_build_card_name_index() -> None:
    index = build_card_name_index(
        [{"id": "01", "name": "The Fool"}],
        [{"id": "c01", "name": "Ace of Cups"}],
    )
    assert index["01"] == "The Fool"
    assert index["c01"] == "Ace of Cups"
