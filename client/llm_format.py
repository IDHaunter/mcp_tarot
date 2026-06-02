"""Format structured tarot data as compact text for LLM prompts."""

from __future__ import annotations

import json
import logging
from typing import Any

from client.config import FormatConfig


def format_card_title(card: dict[str, Any], fmt: FormatConfig) -> str:
    """Build display title with orientation embedded (no duplicate flags)."""
    name = str(card.get("name") or card.get("id") or "Unknown")
    if card.get("reversed"):
        return f"{name} ({fmt.reversed_suffix})"
    return name


def format_card_for_llm(
    card: dict[str, Any],
    fmt: FormatConfig,
    *,
    index: int | None = None,
    header_label: str | None = None,
) -> str:
    """Render one drawn card as a compact human-readable block."""
    title = format_card_title(card, fmt)
    label = header_label or fmt.card_label
    if index is not None:
        header = f"{label} {index}: {title}"
    else:
        header = f"{label}: {title}"

    lines = [header]
    meanings = card.get("meanings")
    if isinstance(meanings, dict):
        for key, field_label in fmt.meaning_label_pairs():
            value = meanings.get(key)
            if value:
                lines.append(f"{field_label}: {value}")

    return "\n".join(lines)


def build_card_name_index(*card_lists: list[dict[str, Any]]) -> dict[str, str]:
    """Map card id to display name from one or more card lists."""
    index: dict[str, str] = {}
    for cards in card_lists:
        for card in cards:
            card_id = str(card.get("id", ""))
            if card_id and card.get("name"):
                index[card_id] = str(card["name"])
    return index


def resolve_card_display_name(card_id: str, name_index: dict[str, str]) -> str:
    """Resolve a card id to its display name for interaction lines."""
    cached = name_index.get(card_id)
    if cached:
        return cached

    try:
        from server.card_store import CardNotFoundError, load_card_data

        data = load_card_data(card_id)
        return str(data.get("name") or card_id)
    except (CardNotFoundError, OSError, ValueError, ImportError):
        return card_id


def _pair_relation_line(
    pair: dict[str, Any],
    name_index: dict[str, str],
    fmt: FormatConfig,
) -> str:
    """Format one pair dependency as a bullet line."""
    id_a = str(pair.get("card_a", {}).get("id", ""))
    id_b = str(pair.get("card_b", {}).get("id", ""))
    name_a = resolve_card_display_name(id_a, name_index)
    name_b = resolve_card_display_name(id_b, name_index)

    parts: list[str] = []
    if text := pair.get("from_a_to_b"):
        parts.append(str(text))
    if text := pair.get("from_b_to_a"):
        parts.append(str(text))

    relation_text = ", ".join(parts) if parts else fmt.no_relation_text
    return f"* {name_a} + {name_b}:\n  {relation_text}"


def format_pair_relations_for_llm(
    pairs: list[dict[str, Any]],
    name_index: dict[str, str],
    fmt: FormatConfig,
    *,
    heading: str | None = None,
) -> str:
    """Render pairwise card influences as compact readable lines."""
    if not pairs:
        return ""

    title = heading or fmt.interactions_heading
    lines = [f"{title}:", ""]
    lines.extend(_pair_relation_line(pair, name_index, fmt) for pair in pairs)
    return "\n".join(lines)


def format_reading_info_for_llm(
    info: dict[str, Any],
    fmt: FormatConfig,
) -> str:
    """Format spread MCP response (cards + pair_dependencies) for the LLM."""
    cards = info.get("cards", [])
    if not isinstance(cards, list):
        cards = []

    blocks: list[str] = []
    for index, card in enumerate(cards, start=1):
        if isinstance(card, dict):
            blocks.append(format_card_for_llm(card, fmt, index=index))

    pairs = info.get("pair_dependencies", [])
    if isinstance(pairs, list) and pairs:
        name_index = build_card_name_index(cards)
        pair_text = format_pair_relations_for_llm(pairs, name_index, fmt)
        if pair_text:
            if blocks:
                blocks.append("")
            blocks.append(pair_text)

    return "\n\n".join(blocks)


def format_clarification_for_llm(
    extra: dict[str, Any],
    fmt: FormatConfig,
    *,
    drawn_cards: list[dict[str, Any]] | None = None,
) -> str:
    """Format clarification MCP response (card + influences) for the LLM."""
    blocks: list[str] = []
    clarification = extra.get("card")
    drawn = drawn_cards or []

    if isinstance(clarification, dict):
        blocks.append(
            format_card_for_llm(
                clarification,
                fmt,
                header_label=fmt.clarification_card_label,
            )
        )

    influences = extra.get("influences", [])
    if isinstance(influences, list) and influences:
        name_index = build_card_name_index(
            drawn, [clarification] if clarification else []
        )
        pair_text = format_pair_relations_for_llm(
            influences,
            name_index,
            fmt,
            heading=fmt.clarification_interactions_heading,
        )
        if pair_text:
            if blocks:
                blocks.append("")
            blocks.append(pair_text)

    return "\n\n".join(blocks)


def build_llm_prompt(template: str, **kwargs: Any) -> str:
    """Apply template placeholders to build the final user message."""
    return template.format(**kwargs)


def log_prompt_size_comparison(
    logger: logging.Logger,
    structured: Any,
    formatted: str,
    *,
    label: str,
) -> None:
    """Log formatted vs JSON size for prompt tuning."""
    json_payload = json.dumps(structured, ensure_ascii=False, indent=2)
    json_len = len(json_payload)
    formatted_len = len(formatted)
    ratio = (100.0 * formatted_len / json_len) if json_len else 0.0
    logger.info(
        "%s prompt block: formatted=%d chars json=%d chars (%.0f%% of json size)",
        label,
        formatted_len,
        json_len,
        ratio,
    )
    logger.debug("%s formatted prompt block:\n%s", label, formatted)
