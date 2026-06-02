"""Tests for server.card_store."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.card_store import (
    CardNotFoundError,
    build_card_payload,
    card_data_path,
    is_major_arcana,
    load_card_data,
    parse_minor_arcana,
)
from server.locale_registry import locale_cards_root


class TestIsMajorArcana:
    """Tests for is_major_arcana."""

    @pytest.mark.parametrize("card_id", ["01", "10", "22"])
    def test_major_ids(self, card_id: str) -> None:
        assert is_major_arcana(card_id) is True

    @pytest.mark.parametrize("card_id", ["c01", "p14", "s08", "w11", "1", "023"])
    def test_non_major_ids(self, card_id: str) -> None:
        assert is_major_arcana(card_id) is False


class TestParseMinorArcana:
    """Tests for parse_minor_arcana."""

    @pytest.mark.parametrize(
        ("card_id", "suit", "rank"),
        [
            ("c01", "cups", "01"),
            ("p14", "pentacles", "14"),
            ("s08", "swords", "08"),
            ("w11", "wands", "11"),
        ],
    )
    def test_valid_minor_ids(
        self, card_id: str, suit: str, rank: str
    ) -> None:
        assert parse_minor_arcana(card_id) == (suit, rank)

    @pytest.mark.parametrize("card_id", ["", "01", "x01", "c1", "c001", "c0x"])
    def test_invalid_minor_ids(self, card_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid minor arcana"):
            parse_minor_arcana(card_id)


class TestCardDataPath:
    """Tests for card_data_path."""

    def test_major_path(self) -> None:
        root = locale_cards_root("en")
        path = card_data_path("01")
        assert path == root / "major" / "01.json"
        assert path.is_file()

    def test_minor_path(self) -> None:
        root = locale_cards_root("en")
        path = card_data_path("c05")
        assert path == root / "minor" / "cups" / "05.json"
        assert path.is_file()

    def test_missing_major_raises(self) -> None:
        with pytest.raises(CardNotFoundError, match="Card data not found"):
            card_data_path("99")

    def test_invalid_id_raises(self) -> None:
        with pytest.raises(CardNotFoundError):
            card_data_path("invalid")


class TestLoadCardData:
    """Tests for load_card_data."""

    def test_load_major_has_name(self) -> None:
        data = load_card_data("01")
        assert data["name"] == "The Fool"
        assert "upright" in data
        assert "reversed" in data
        assert "relations" in data
        assert "meaning_for_today" not in data
        assert "meaning_for_today" in data["upright"]
        assert "card_advice" in data["upright"]
        assert "meaning_for_today" in data["reversed"]
        assert "card_advice" in data["reversed"]

    def test_load_minor_has_name(self) -> None:
        data = load_card_data("w01")
        assert "Ace" in data["name"]
        assert "Wands" in data["name"]


class TestBuildCardPayload:
    """Tests for build_card_payload."""

    def test_upright_payload(self) -> None:
        payload = build_card_payload("01", reversed_=False)
        assert payload["id"] == "01"
        assert payload["reversed"] is False
        assert payload["orientation"] == "upright"
        assert payload["name"] == "The Fool"
        assert "card_data" not in payload
        assert payload["meanings"] == load_card_data("01")["upright"]
        assert payload["meaning_for_today"]
        assert payload["card_advice"]

    def test_reversed_payload(self) -> None:
        payload = build_card_payload("01", reversed_=True)
        assert payload["orientation"] == "reversed"
        assert "card_data" not in payload
        assert payload["meanings"] == load_card_data("01")["reversed"]

    def test_minor_payload(self) -> None:
        payload = build_card_payload("c01", reversed_=False)
        assert payload["id"] == "c01"
        assert "Cups" in payload["name"]

    def test_payload_has_no_relations_or_duplicate_orientation(self) -> None:
        raw = load_card_data("01")
        payload = build_card_payload("01", reversed_=False)
        assert "relations" not in payload
        assert "upright" not in payload
        assert payload["reversed"] is False
        assert set(payload.keys()) == {
            "id",
            "reversed",
            "name",
            "meaning_for_today",
            "card_advice",
            "orientation",
            "meanings",
        }
        assert payload["meanings"] == raw["upright"]
