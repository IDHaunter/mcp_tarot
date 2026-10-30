"""MCP server application exposing tarot tools."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from server.card_store import build_card_payload
from server.deck import generate_tarot_sequence
from server.models import (
    AlreadyDrawnCards,
    CardInformationCards,
    TarotCardInput,
    TarotSequence,
    cards_to_dicts,
)
from server.relations import pair_dependencies

mcp = FastMCP(
    "tarot",
    instructions=(
        "Tarot fortune-telling MCP server for LLM agents. "
        "Reading workflow: (1) Call generate_tarot_sequence once at the "
        "start of a new reading and preserve the returned sequence. "
        "(2) Select positions from that sequence and call "
        "get_card_information with those cards' id and reversed values. "
        "(3) For follow-up clarification, call get_additional_card with "
        "the original sequence and already-drawn cards — never regenerate "
        "the sequence mid-reading."
    ),
)


@mcp.tool(name="generate_tarot_sequence")
def tool_generate_tarot_sequence() -> dict[str, dict[str, str | bool]]:
    """Generate a shuffled sequence containing all 78 tarot cards.

    Use this tool once at the beginning of a new reading to create the
    deck order for that reading. Do not call it again when drawing
    additional cards for clarification — regenerating would invalidate
    previously selected positions.

    Returns:
        A mapping of position keys ``\"1\"`` through ``\"78\"`` to card
        objects. Each card object has:
        - ``id`` (str): card identifier (Major ``01``-``22`` or Minor
          ``c|p|s|w`` + ``01``-``14``)
        - ``reversed`` (bool): orientation for this draw

    Workflow:
        Preserve the full returned sequence for the entire reading.
        Choose positions from it, then pass the corresponding card
        ``id``/``reversed`` pairs to ``get_card_information``. For
        follow-ups, pass this same sequence to ``get_additional_card``.
    """
    return generate_tarot_sequence()


@mcp.tool(name="get_card_information")
def tool_get_card_information(
    cards: CardInformationCards,
) -> dict[str, Any]:
    """Retrieve detailed interpretations for one or more selected cards.

    Use this tool after choosing cards from a generated sequence (initial
    spread), or whenever you need interpretations for an updated group of
    cards in the current reading.

    Input:
        ``cards`` — non-empty list (1–78) of objects, each with:
        - ``id`` (str, required): tarot card identifier
        - ``reversed`` (bool, optional): defaults to ``false`` if omitted;
          must be a JSON boolean (strings/integers are rejected)
        Duplicate card ids are rejected.

    Returns:
        ``{\"cards\": [...], \"pair_dependencies\": [...]}`` where:
        - ``cards`` is the list of card payloads (id, reversed, name,
          meaning_for_today, card_advice, orientation, meanings)
        - ``pair_dependencies`` describes pairwise interactions between
          every unique pair of selected cards; consider these when
          interpreting a multi-card spread

    Related tools:
        Call ``generate_tarot_sequence`` first to obtain card ids and
        orientations. Use ``get_additional_card`` later to draw one more
        card from that same sequence without regenerating it.
    """
    normalized = cards_to_dicts(cards)
    payloads = [
        build_card_payload(str(card["id"]), bool(card["reversed"]))
        for card in normalized
    ]
    dependencies = pair_dependencies(normalized)
    return {"cards": payloads, "pair_dependencies": dependencies}


@mcp.tool(name="get_additional_card")
def tool_get_additional_card(
    position_id: Annotated[
        str,
        Field(
            description=(
                "Position key in ``sequence`` to draw "
                "(for example ``\"15\"``). Must exist in the sequence."
            ),
        ),
    ],
    sequence: TarotSequence,
    already_drawn: AlreadyDrawnCards,
) -> dict[str, Any]:
    """Draw one additional card from an existing shuffled sequence.

    Use this tool for follow-up questions and clarification during an
    ongoing reading. It must not generate a new sequence — always reuse
    the sequence returned by ``generate_tarot_sequence`` for this reading.

    Input:
        - ``position_id``: position key in ``sequence`` (e.g. ``\"15\"``)
        - ``sequence``: the original full shuffled deck from
          ``generate_tarot_sequence`` (keys ``\"1\"``..``\"78\"``, each
          value ``{\"id\", \"reversed\"}``)
        - ``already_drawn``: cards already selected in this reading
          (same shape as ``get_card_information`` card entries). Duplicate
          ids in this list are rejected.

    Behavior:
        Looks up the card at ``position_id``, refuses if that card id was
        already selected, then returns the new card interpretation plus
        its pairwise relationships with previously drawn cards.

    Returns:
        ``{\"position_id\", \"card\", \"influences\"}`` where ``card`` is
        the standard card payload and ``influences`` are pair-dependency
        entries involving the newly drawn card.

    Related tools:
        Requires a preserved sequence from ``generate_tarot_sequence``.
        After drawing, you may call ``get_card_information`` again with
        the full updated set of cards if you need a complete re-read.
    """
    if position_id not in sequence:
        raise ValueError(f"Invalid position_id: {position_id}")

    drawn = cards_to_dicts(already_drawn)
    drawn_ids = {str(card["id"]) for card in drawn}

    slot: TarotCardInput = sequence[position_id]
    card_id = slot.id
    reversed_ = slot.reversed

    if card_id in drawn_ids:
        raise ValueError(
            f"Card at position {position_id} was already drawn"
        )

    payload = build_card_payload(card_id, reversed_)
    all_for_pairs = drawn + [{"id": card_id, "reversed": reversed_}]
    influences = pair_dependencies(all_for_pairs)
    new_card_pairs = [
        pair
        for pair in influences
        if pair["card_a"]["id"] == card_id or pair["card_b"]["id"] == card_id
    ]

    return {
        "position_id": position_id,
        "card": payload,
        "influences": new_card_pairs,
    }
