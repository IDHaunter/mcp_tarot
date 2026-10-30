"""Pydantic input models for MCP tarot tools."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# Major Arcana: 01-22. Minor Arcana: c/p/s/w + 01-14.
CARD_ID_PATTERN = r"^(?:0[1-9]|1[0-9]|2[0-2]|[cpsw](?:0[1-9]|1[0-4]))$"
_CARD_ID_RE = re.compile(CARD_ID_PATTERN)


class TarotCardInput(BaseModel):
    """A selected tarot card with id and orientation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        description=(
            "Unique tarot card identifier. "
            "Major Arcana: 01-22. "
            "Minor Arcana: c01-c14, p01-p14, "
            "s01-s14, w01-w14."
        ),
        pattern=CARD_ID_PATTERN,
    )

    reversed: bool = Field(
        default=False,
        strict=True,
        description=(
            "True if the card is reversed (upside down); "
            "false if the card is upright."
        ),
    )


def is_valid_card_id_format(card_id: str) -> bool:
    """Return True if ``card_id`` matches the deck identifier convention."""
    return bool(_CARD_ID_RE.fullmatch(card_id))


def _reject_duplicate_card_ids(
    cards: list[TarotCardInput],
) -> list[TarotCardInput]:
    """Reject collections that contain the same card id more than once."""
    seen: set[str] = set()
    for card in cards:
        if card.id in seen:
            raise ValueError(f"Duplicate card id is not allowed: {card.id}")
        seen.add(card.id)
    return cards


CardInformationCards = Annotated[
    list[TarotCardInput],
    Field(
        min_length=1,
        max_length=78,
        description=(
            "One or more selected cards to interpret. "
            "Each item must include ``id`` and may include ``reversed``. "
            "Must not be empty, must not exceed 78 cards, "
            "and must not contain duplicate card ids."
        ),
    ),
    AfterValidator(_reject_duplicate_card_ids),
]

AlreadyDrawnCards = Annotated[
    list[TarotCardInput],
    Field(
        description=(
            "Cards already selected in the current reading. "
            "Each item must include ``id`` and may include ``reversed``. "
            "Must not contain duplicate card ids. "
            "May be empty if no cards have been drawn yet."
        ),
    ),
    AfterValidator(_reject_duplicate_card_ids),
]

TarotSequence = Annotated[
    dict[str, TarotCardInput],
    Field(
        description=(
            "Full shuffled deck from ``generate_tarot_sequence``. "
            "Keys are position strings ``\"1\"``..``\"78\"``. "
            "Each value is an object with ``id`` and ``reversed``."
        ),
    ),
]


def cards_to_dicts(cards: list[TarotCardInput]) -> list[dict[str, str | bool]]:
    """Convert validated card models to the dict shape used by relations."""
    return [{"id": card.id, "reversed": card.reversed} for card in cards]
