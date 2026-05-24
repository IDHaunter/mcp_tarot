"""MCP server application exposing tarot tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from server.card_store import CardNotFoundError, build_card_payload
from server.deck import generate_tarot_sequence
from server.relations import pair_dependencies

mcp = FastMCP(
    "tarot",
    instructions=(
        "Tarot fortune telling server. Tools: shuffle deck, load card "
        "interpretations with pair relations, draw one more card from a sequence."
    ),
)


def _parse_cards_argument(cards: list[dict[str, Any]]) -> list[dict[str, str | bool]]:
    """Normalize card entries from tool input."""
    normalized: list[dict[str, str | bool]] = []
    for entry in cards:
        if "id" not in entry:
            raise ValueError("Each card entry must include 'id'")
        normalized.append(
            {
                "id": str(entry["id"]),
                "reversed": bool(entry.get("reversed", False)),
            }
        )
    return normalized


@mcp.tool(name="generate_tarot_sequence")
def tool_generate_tarot_sequence() -> dict[str, dict[str, str | bool]]:
    """Generate a randomly shuffled deck of 78 cards with orientations.

    Returns:
        Sequence keyed by position ``1``..``78`` with ``id`` and ``reversed``.
    """
    return generate_tarot_sequence()


@mcp.tool(name="get_card_information")
def tool_get_card_information(
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return card JSON payloads and pairwise relation interpretations.

    Args:
        cards: List of objects with ``id`` (str) and ``reversed`` (bool).

    Returns:
        Dict with ``cards`` and ``pair_dependencies`` arrays.
    """
    try:
        normalized = _parse_cards_argument(cards)
        payloads = [
            build_card_payload(str(c["id"]), bool(c["reversed"])) for c in normalized
        ]
        dependencies = pair_dependencies(normalized)
        return {"cards": payloads, "pair_dependencies": dependencies}
    except (CardNotFoundError, ValueError) as exc:
        return {"error": str(exc)}


@mcp.tool(name="get_additional_card")
def tool_get_additional_card(
    position_id: str,
    sequence: dict[str, dict[str, str | bool]],
    already_drawn: list[dict[str, Any]],
) -> dict[str, Any]:
    """Draw one card from the deck sequence by position.

    Args:
        position_id: Position key in ``sequence`` (e.g. ``"15"``).
        sequence: Full shuffled deck from ``generate_tarot_sequence``.
        already_drawn: Cards already selected, each with ``id`` and ``reversed``.

    Returns:
        Dict with the new card payload and influences on drawn cards.
    """
    try:
        if position_id not in sequence:
            raise ValueError(f"Invalid position_id: {position_id}")

        drawn = _parse_cards_argument(already_drawn)
        drawn_ids = {str(c["id"]) for c in drawn}

        slot = sequence[position_id]
        card_id = str(slot["id"])
        reversed_ = bool(slot["reversed"])

        if card_id in drawn_ids:
            raise ValueError(f"Card at position {position_id} was already drawn")

        payload = build_card_payload(card_id, reversed_)
        all_for_pairs = drawn + [{"id": card_id, "reversed": reversed_}]
        influences = pair_dependencies(all_for_pairs)
        new_card_pairs = [
            p
            for p in influences
            if p["card_a"]["id"] == card_id or p["card_b"]["id"] == card_id
        ]

        return {
            "position_id": position_id,
            "card": payload,
            "influences": new_card_pairs,
        }
    except (CardNotFoundError, ValueError) as exc:
        return {"error": str(exc)}
