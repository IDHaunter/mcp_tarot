"""Tests for server.models input validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.models import (
    TarotCardInput,
    _reject_duplicate_card_ids,
    is_valid_card_id_format,
)


class TestCardIdFormat:
    """Card ID convention validation."""

    @pytest.mark.parametrize("card_id", ["01", "09", "10", "22"])
    def test_valid_major_arcana_ids(self, card_id: str) -> None:
        assert is_valid_card_id_format(card_id) is True
        assert TarotCardInput(id=card_id).id == card_id

    @pytest.mark.parametrize(
        "card_id",
        [
            "c01",
            "c14",
            "p01",
            "p14",
            "s01",
            "s14",
            "w01",
            "w14",
        ],
    )
    def test_valid_minor_arcana_ids(self, card_id: str) -> None:
        assert is_valid_card_id_format(card_id) is True
        assert TarotCardInput(id=card_id).id == card_id

    @pytest.mark.parametrize(
        "card_id",
        [
            "",
            "00",
            "23",
            "1",
            "001",
            "c00",
            "c15",
            "x01",
            "C01",
            "invalid",
            "c1",
            "c001",
        ],
    )
    def test_invalid_card_id_formats(self, card_id: str) -> None:
        assert is_valid_card_id_format(card_id) is False
        with pytest.raises(ValidationError):
            TarotCardInput(id=card_id)


class TestTarotCardInput:
    """TarotCardInput field rules."""

    def test_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TarotCardInput.model_validate({"reversed": False})

    def test_missing_reversed_defaults_to_false(self) -> None:
        card = TarotCardInput.model_validate({"id": "01"})
        assert card.reversed is False

    def test_bool_true_and_false_accepted(self) -> None:
        assert TarotCardInput(id="01", reversed=True).reversed is True
        assert TarotCardInput(id="01", reversed=False).reversed is False

    @pytest.mark.parametrize("value", ["false", "true", "False", "True", "0", "1"])
    def test_string_reversed_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            TarotCardInput.model_validate({"id": "01", "reversed": value})

    @pytest.mark.parametrize("value", [0, 1])
    def test_integer_reversed_rejected(self, value: int) -> None:
        with pytest.raises(ValidationError):
            TarotCardInput.model_validate({"id": "01", "reversed": value})

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TarotCardInput.model_validate(
                {"id": "01", "reversed": False, "name": "The Fool"}
            )


class TestDuplicateCardIds:
    """Collection uniqueness helper."""

    def test_unique_cards_pass(self) -> None:
        cards = [
            TarotCardInput(id="01"),
            TarotCardInput(id="c05", reversed=True),
        ]
        assert _reject_duplicate_card_ids(cards) == cards

    def test_duplicate_ids_rejected(self) -> None:
        cards = [
            TarotCardInput(id="01"),
            TarotCardInput(id="01", reversed=True),
        ]
        with pytest.raises(ValueError, match="Duplicate card id"):
            _reject_duplicate_card_ids(cards)
