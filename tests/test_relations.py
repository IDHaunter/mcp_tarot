"""Tests for server.relations."""

from __future__ import annotations

from typing import Any

import pytest

from server.card_store import load_card_data
from server.relations import (
    lookup_relation,
    pair_dependencies,
    relation_key_for_card,
)


class TestRelationKeyForCard:
    """Tests for relation_key_for_card."""

    def test_major_key(self) -> None:
        assert relation_key_for_card("07") == ("major", "07")

    def test_minor_key(self) -> None:
        assert relation_key_for_card("c03") == ("cups", "03")


class TestLookupRelation:
    """Tests for lookup_relation."""

    @pytest.fixture
    def fool_data(self) -> dict[str, Any]:
        return load_card_data("01")

    def test_major_to_major_relation(self, fool_data: dict[str, Any]) -> None:
        text = lookup_relation(fool_data, "02")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_major_to_minor_relation(self, fool_data: dict[str, Any]) -> None:
        text = lookup_relation(fool_data, "c01")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_unknown_relation_returns_none(self, fool_data: dict[str, Any]) -> None:
        empty_source: dict[str, Any] = {"relations": {"major": {}, "minor": {}}}
        assert lookup_relation(empty_source, "02") is None


class TestPairDependencies:
    """Tests for pair_dependencies."""

    def test_single_card_no_pairs(self) -> None:
        cards = [{"id": "01", "reversed": False}]
        assert pair_dependencies(cards) == []

    def test_two_cards_one_pair(self) -> None:
        cards = [
            {"id": "01", "reversed": False},
            {"id": "02", "reversed": True},
        ]
        pairs = pair_dependencies(cards)
        assert len(pairs) == 1
        pair = pairs[0]
        assert pair["card_a"] == {"id": "01"}
        assert pair["card_b"] == {"id": "02"}
        assert "reversed" not in pair["card_a"]
        assert "reversed" not in pair["card_b"]
        assert isinstance(pair["from_a_to_b"], (str, type(None)))
        assert isinstance(pair["from_b_to_a"], (str, type(None)))

    def test_three_cards_three_pairs(self) -> None:
        cards = [
            {"id": "01", "reversed": False},
            {"id": "02", "reversed": False},
            {"id": "c01", "reversed": True},
        ]
        pairs = pair_dependencies(cards)
        assert len(pairs) == 3

    def test_fool_and_magician_have_bidirectional_text(self) -> None:
        cards = [
            {"id": "01", "reversed": False},
            {"id": "02", "reversed": False},
        ]
        pair = pair_dependencies(cards)[0]
        assert pair["from_a_to_b"]
        assert pair["from_b_to_a"]
