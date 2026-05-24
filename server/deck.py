"""Tarot deck generation."""

from __future__ import annotations

import random


def generate_tarot_sequence() -> dict[str, dict[str, str | bool]]:
    """Generate a randomly shuffled sequence of all 78 Tarot cards.

    Builds a complete deck (22 Major + 56 Minor Arcana), shuffles it, and
    assigns a random orientation to each card.

    Returns:
        dict[str, dict[str, str | bool]]: Keys are positions "1".."78";
        values contain card ``id`` and ``reversed`` flag.
    """
    deck: list[str] = []

    for i in range(1, 23):
        deck.append(f"{i:02d}")

    categories: list[str] = ["c", "p", "s", "w"]
    for category in categories:
        for number in range(1, 15):
            deck.append(f"{category}{number:02d}")

    random.shuffle(deck)

    sequence: dict[str, dict[str, str | bool]] = {}
    for index, card_id in enumerate(deck, start=1):
        sequence[str(index)] = {
            "id": card_id,
            "reversed": random.choice([True, False]),
        }

    return sequence
