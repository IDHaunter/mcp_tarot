"""Resolve pairwise card relation texts from card JSON data."""

from __future__ import annotations

from typing import Any

from server.card_store import is_major_arcana, load_card_data, parse_minor_arcana


def relation_key_for_card(card_id: str) -> tuple[str, str]:
    """Return relation lookup type and key for a target card id.

    Args:
        card_id: Major or minor arcana id.

    Returns:
        (``major``, rank) or (suit_name, rank) for minor lookups in relations blocks.
    """
    if is_major_arcana(card_id):
        return "major", card_id
    suit, rank = parse_minor_arcana(card_id)
    return suit, rank


def lookup_relation(source_data: dict[str, Any], target_id: str) -> str | None:
    """Find relation text from source card data toward target card.

    Args:
        source_data: Full JSON for the source card.
        target_id: Id of the other card.

    Returns:
        Relation description or None if not defined.
    """
    relations = source_data.get("relations", {})
    rel_type, rel_key = relation_key_for_card(target_id)

    if rel_type == "major":
        block = relations.get("major", {})
        return block.get(rel_key)

    minor_block = relations.get("minor", {})
    suit_block = minor_block.get(rel_type, {})
    return suit_block.get(rel_key)


def pair_dependencies(
    cards: list[dict[str, str | bool]],
) -> list[dict[str, Any]]:
    """Build pairwise influence texts for all unique card pairs.

    Args:
        cards: List of dicts with ``id`` and ``reversed`` keys.

    Returns:
        List of pair dependency objects with texts in both directions.
    """
    pairs: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {
        str(c["id"]): load_card_data(str(c["id"])) for c in cards
    }

    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            id_a = str(cards[i]["id"])
            id_b = str(cards[j]["id"])
            data_a = loaded[id_a]
            data_b = loaded[id_b]
            pairs.append(
                {
                    "card_a": {"id": id_a, "reversed": bool(cards[i]["reversed"])},
                    "card_b": {"id": id_b, "reversed": bool(cards[j]["reversed"])},
                    "from_a_to_b": lookup_relation(data_a, id_b),
                    "from_b_to_a": lookup_relation(data_b, id_a),
                }
            )

    return pairs
