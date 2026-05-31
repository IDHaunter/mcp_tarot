"""Load tarot card JSON data from the server data directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"

_MINOR_PREFIX_TO_SUIT: dict[str, str] = {
    "c": "cups",
    "p": "pentacles",
    "s": "swords",
    "w": "wands",
}


class CardNotFoundError(ValueError):
    """Raised when a card id does not map to a data file."""


def is_major_arcana(card_id: str) -> bool:
    """Return True if ``card_id`` is a two-digit major arcana code."""
    return len(card_id) == 2 and card_id.isdigit()


def parse_minor_arcana(card_id: str) -> tuple[str, str]:
    """Parse minor id (e.g. ``c05``) into suit folder name and rank file stem.

    Args:
        card_id: Minor arcana id like ``c01`` or ``p14``.

    Returns:
        Tuple of (suit_name, rank) e.g. (``cups``, ``05``).

    Raises:
        ValueError: If the id format is invalid.
    """
    if len(card_id) != 3 or card_id[0] not in _MINOR_PREFIX_TO_SUIT:
        raise ValueError(f"Invalid minor arcana id: {card_id}")
    suit = _MINOR_PREFIX_TO_SUIT[card_id[0]]
    rank = card_id[1:]
    if not rank.isdigit():
        raise ValueError(f"Invalid minor arcana id: {card_id}")
    return suit, rank


def card_data_path(card_id: str) -> Path:
    """Resolve filesystem path for a card JSON file.

    Args:
        card_id: Major (``01``..``22``) or minor (``c01`` etc.) id.

    Returns:
        Path to the card JSON file.

    Raises:
        CardNotFoundError: If the id cannot be resolved.
    """
    if is_major_arcana(card_id):
        path = DATA_DIR / "major" / f"{card_id}.json"
    else:
        try:
            suit, rank = parse_minor_arcana(card_id)
        except ValueError as exc:
            raise CardNotFoundError(str(exc)) from exc
        path = DATA_DIR / "minor" / suit / f"{rank}.json"

    if not path.is_file():
        raise CardNotFoundError(f"Card data not found for id: {card_id}")
    return path


def load_card_data(card_id: str) -> dict[str, Any]:
    """Load raw card JSON by id.

    Args:
        card_id: Tarot card id string.

    Returns:
        Parsed JSON object for the card.

    Raises:
        CardNotFoundError: If the card file is missing.
    """
    path = card_data_path(card_id)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_card_payload(card_id: str, reversed_: bool) -> dict[str, Any]:
    """Build API payload for one drawn card including active meanings.

    Args:
        card_id: Tarot card id.
        reversed_: Whether the card is reversed.

    Returns:
        Card dict with id, orientation, name, advice fields, and active meanings.
    """
    data = load_card_data(card_id)
    orientation_key = "reversed" if reversed_ else "upright"
    orientation_data = data.get(orientation_key, {})
    if not isinstance(orientation_data, dict):
        orientation_data = {}

    return {
        "id": card_id,
        "reversed": reversed_,
        "name": data.get("name", ""),
        "meaning_for_today": str(orientation_data.get("meaning_for_today", "")),
        "card_advice": str(orientation_data.get("card_advice", "")),
        "orientation": orientation_key,
        "meanings": orientation_data,
    }
