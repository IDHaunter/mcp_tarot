"""Streamlit web interface for the Tarot MCP client.

Run from the project root:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image

from client.config import AppConfig, load_config
from client.llm import LLMClient, LLMError
from client.llm_format import (
    build_llm_prompt,
    format_card_for_llm,
    format_clarification_for_llm,
    format_reading_info_for_llm,
    log_prompt_size_comparison,
)
from client.logging_setup import setup_logging
from client.mcp_session import TarotMCPClient, open_tarot_mcp

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "client.yaml"

logger = logging.getLogger("client.streamlit_app")

IMAGE_ROOT = (
    ROOT
    / "server"
    / "data"
    / "images"
    / "rider_waite_smith"
)

BACK_IMAGE_PATH = IMAGE_ROOT / "back.png"


@st.cache_data
def _get_back_image_data_uri() -> str:
    """Return the card-back image as an embeddable CSS data URI."""
    if not BACK_IMAGE_PATH.is_file():
        return ""

    mime_type = "image/png" if BACK_IMAGE_PATH.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(BACK_IMAGE_PATH.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_card_table_styles() -> None:
    """Style card-pick buttons as card backs with a clear selected border."""
    back_image = _get_back_image_data_uri()
    card_background = (
        f'background-image: url("{back_image}");'
        if back_image
        else "background-image: none;"
    )
    card_button_selector = (
        'div[class*="st-key-card_pick_"] button, '
        'div[class*="st-key-card_clarify_"] button'
    )
    card_button_content_selector = (
        'div[class*="st-key-card_pick_"] button div[data-testid="stMarkdownContainer"], '
        'div[class*="st-key-card_clarify_"] button div[data-testid="stMarkdownContainer"]'
    )
    card_button_hover_selector = (
        'div[class*="st-key-card_pick_"] button:hover, '
        'div[class*="st-key-card_clarify_"] button:hover'
    )
    card_button_focus_selector = (
        'div[class*="st-key-card_pick_"] button:focus-visible, '
        'div[class*="st-key-card_clarify_"] button:focus-visible'
    )
    selected_button_selector = (
        'div[class*="st-key-card_pick_"] button[kind="primary"], '
        'div[class*="st-key-card_pick_"] button[data-testid="stBaseButton-primary"], '
        'div[class*="st-key-card_clarify_"] button[kind="primary"], '
        'div[class*="st-key-card_clarify_"] button[data-testid="stBaseButton-primary"]'
    )

    css = f"""
    <style>
    {card_button_selector} {{
        width: 100% !important;
        height: 104px !important;
        min-height: 104px !important;
        padding: 0 !important;
        {card_background}
        background-position: center center !important;
        background-repeat: no-repeat !important;
        background-size: contain !important;
        background-color: #171526 !important;
        border: 2px solid rgba(190, 170, 135, 0.38) !important;
        border-radius: 7px !important;
        box-shadow: none !important;
        color: transparent !important;
        font-size: 0 !important;
        line-height: 0 !important;
        transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }}
    {card_button_content_selector} {{
        visibility: hidden !important;
        font-size: 0 !important;
    }}
    {card_button_hover_selector} {{
        border-color: #c4a66a !important;
        box-shadow: 0 0 0 1px rgba(196, 166, 106, 0.35) !important;
        transform: translateY(-2px);
    }}
    {card_button_focus_selector} {{
        outline: 2px solid #d8bd82 !important;
        outline-offset: 2px !important;
    }}
    {selected_button_selector} {{
        border: 4px solid #f2c85b !important;
        box-shadow: 0 0 0 2px rgba(242, 200, 91, 0.48),
                    0 0 16px rgba(242, 200, 91, 0.42) !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


LIBRARY_COLUMNS = 6
CARDS_PER_ROW = 15

# Card fields that should not be printed as "description" text.
HIDDEN_CARD_FIELDS = {
    "id",
    "reversed",
    "name",
    "display_name",
    "title",
    "card_name",
    "slug",
    "image",
    "image_path",
    "image_url",
}

TEXT = {
    "en": {
        "title": "Tarot reading",
        "subtitle": "Ask a question, choose your cards, and explore the reading.",
        "question": "What would you like guidance on?",
        "question_placeholder": "Write your question here…",
        "shuffle": "Shuffle the deck",
        "shuffle_help": "Creates a new random deck. Card identities stay hidden until you draw them.",
        "deck_ready": "The deck is shuffled. Choose the positions of the cards you want to draw.",
        "positions": "Choose card positions",
        "positions_help": "Click the card backs you want to draw. Three cards are recommended.",
        "select_card": "Select card {position}",
        "draw": "Draw cards and interpret",
        "new_reading": "Start a new reading",
        "reading": "Your reading",
        "selected_cards": "Cards in this spread",
        "clarification": "Clarify the reading",
        "clarification_help": "Choose a card back. Cards already drawn are shown face up and cannot be selected.",
        "clarification_position": "Position for the additional card",
        "draw_extra": "Draw clarification card",
        "followup": "Ask a follow-up question",
        "followup_placeholder": "Ask something about this reading…",
        "send": "Ask",
        "no_question": "Please enter a question first.",
        "no_positions": "Choose at least one card position.",
        "deck_not_ready": "Shuffle the deck before choosing cards.",
        "mcp_error": "Could not communicate with the tarot server: {error}",
        "llm_error": "Could not get a response from the LLM: {error}",
        "new_topic": "New topic",
        "history_reset": "The previous conversation has been cleared.",
        "drawn": "Drawn",
        "reversed": "Reversed",
        "upright": "Upright",
        "followup_history": "Follow-up conversation",
        "language": "Interface language",
        "config_error": "Could not load configuration: {error}",
        "already_drawn": "That position has already been drawn. Choose another one.",
        "empty_reply": "The LLM returned an empty response.",
        "mode": "Mode",
        "mode_reading": "Reading",
        "mode_library": "Card library",
        "library_title": "Card library",
        "library_subtitle": "All cards of the deck. Press a card to read its description.",
        "library_loading": "Loading the deck…",
        "library_empty": "No cards were returned by the tarot server.",
        "library_count": "{count} cards",
        "library_close": "Close description",
    },
    "ru": {
        "title": "Гадание на Таро",
        "subtitle": "Задайте вопрос, выберите карты и изучите толкование.",
        "question": "На какой вопрос вы хотите получить подсказку?",
        "question_placeholder": "Напишите свой вопрос…",
        "shuffle": "Перетасовать колоду",
        "shuffle_help": "Создаёт новую случайную колоду. Карты остаются неизвестными до вытягивания.",
        "deck_ready": "Колода перетасована. Выберите позиции карт, которые хотите вытянуть.",
        "positions": "Выберите позиции карт",
        "positions_help": "Нажимайте на рубашки карт, чтобы выбрать их. Рекомендуется выбрать три карты.",
        "select_card": "Выбрать карту {position}",
        "draw": "Вытянуть карты и получить толкование",
        "new_reading": "Начать новый расклад",
        "reading": "Ваше толкование",
        "selected_cards": "Карты расклада",
        "clarification": "Уточнить расклад",
        "clarification_help": "Выберите рубашку карты. Уже вытянутые карты показаны лицевой стороной и недоступны для выбора.",
        "clarification_position": "Позиция дополнительной карты",
        "draw_extra": "Вытянуть карту для уточнения",
        "followup": "Задать уточняющий вопрос",
        "followup_placeholder": "Спросите что-нибудь об этом раскладе…",
        "send": "Спросить",
        "no_question": "Сначала введите вопрос.",
        "no_positions": "Выберите хотя бы одну позицию карты.",
        "deck_not_ready": "Сначала перетасуйте колоду.",
        "mcp_error": "Не удалось связаться с сервером Таро: {error}",
        "llm_error": "Не удалось получить ответ от LLM: {error}",
        "new_topic": "Новая тема",
        "history_reset": "Предыдущий диалог очищен.",
        "drawn": "Вытянута",
        "reversed": "Перевёрнутая",
        "upright": "Прямая",
        "followup_history": "Уточняющий диалог",
        "language": "Язык интерфейса",
        "config_error": "Не удалось загрузить конфигурацию: {error}",
        "already_drawn": "Эта позиция уже использована. Выберите другую.",
        "empty_reply": "LLM вернула пустой ответ.",
        "mode": "Режим",
        "mode_reading": "Расклад",
        "mode_library": "Все карты колоды",
        "library_title": "Все карты колоды",
        "library_subtitle": "Все карты колоды. Нажмите на карту, чтобы прочитать её описание.",
        "library_loading": "Загружаем колоду…",
        "library_empty": "Сервер Таро не вернул ни одной карты.",
        "library_count": "Карт: {count}",
        "library_close": "Закрыть описание",
    },
}


def _run_async(coro: Any) -> Any:
    """Run one async MCP operation from Streamlit's synchronous execution flow."""
    return asyncio.run(coro)


@st.cache_resource
def _load_config(locale_override: str) -> AppConfig:
    """Load configuration once per selected locale."""
    config, active_locale = load_config(
        CONFIG_PATH,
        project_root=ROOT,
        locale=locale_override or None,
    )

    if base_url := os.environ.get("LLM_BASE_URL"):
        config.llm.base_url = base_url
    if not config.llm.api_key:
        config.llm.api_key = os.environ.get("OPENAI_API_KEY", "")

    if config.mcp.cwd is None:
        config.mcp.cwd = str(ROOT)
    if config.mcp.command == "python":
        config.mcp.command = sys.executable
    config.mcp.env = {**config.mcp.env, "TAROT_LOCALE": active_locale}

    if level_override := os.environ.get("LOG_LEVEL"):
        config.logging.level = level_override

    global logger

    logger = setup_logging(config.logging, base_dir=ROOT)
    logger.debug("Streamlit app root: %s", ROOT)
    
    return config


def _t(key: str, **kwargs: Any) -> str:
    language = st.session_state.get("locale", "en")
    return TEXT.get(language, TEXT["en"])[key].format(**kwargs)


async def _mcp_call(method: str, *args: Any) -> Any:
    """Open a short-lived MCP session for one tool call."""
    config: AppConfig = st.session_state.config
    async with open_tarot_mcp(config.mcp) as client:
        operation = getattr(client, method)
        return await operation(*args)


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "sequence": {},
        "drawn": [],
        "spread_cards": [],
        "messages": None,
        "question_text": "",
        "reading_text": "",
        "clarification_history": [],
        "selected_positions": [],
        "clarification_selected_position": None,
        "deck_version": 0,
        "deck_ready": False,
        "active_reading": False,
        "locale": os.environ.get("TAROT_LOCALE", ""),
        "mode": "reading",
        "library_cache": {},
        "library_selected": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_reading(reset_history: bool = True) -> None:
    st.session_state.sequence = {}
    st.session_state.drawn = []
    st.session_state.spread_cards = []
    st.session_state.question_text = ""
    st.session_state.reading_text = ""
    st.session_state.clarification_history = []
    st.session_state.selected_positions = []
    st.session_state.clarification_selected_position = None
    st.session_state.deck_ready = False
    st.session_state.active_reading = False
    if reset_history:
        st.session_state.messages = [
            {"role": "system", "content": st.session_state.config.llm.system_prompt}
        ]


def _ask_llm(user_content: str) -> str:
    """Ask the configured LLM and preserve successful turns in session history."""
    messages = st.session_state.messages
    messages.append({"role": "user", "content": user_content})
    try:
        reply = LLMClient(st.session_state.config.llm).chat(messages)
    except LLMError:
        messages.pop()
        raise
    messages.append({"role": "assistant", "content": reply})
    return reply


def _position_label(position: int) -> str:
    slot = st.session_state.sequence.get(str(position), {})
    if not slot:
        return f"{position:02d}"
    # Never show card identity before the user draws it.
    return f"{position:02d}"


def _card_name(card: dict[str, Any]) -> str:
    for key in ("name", "display_name", "title", "card_name"):
        value = card.get(key)
        if value:
            return str(value)
    return str(card.get("id", "Tarot card"))


@st.cache_data
def _get_card_image_files() -> list[str]:
    """Return all card image paths, excluding the deck back."""
    if not IMAGE_ROOT.exists():
        return []

    extensions = {".png", ".jpg", ".jpeg", ".webp"}

    return [
        str(path)
        for path in IMAGE_ROOT.rglob("*")
        if path.is_file()
        and path.name.lower() != "back.png"
        and path.suffix.lower() in extensions
    ]


def _normalize_image_name(value: str) -> str:
    """Normalize a card name for filename matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _card_image_path(card: dict) -> Path | None:
    """Find a card image using its ID or name."""
    if not isinstance(card, dict):
        return None

    card_id = str(card.get("id", "")).lower()

    # Minor Arcana: suit prefix + card number.
    suit_directories = {
        "c": "cups",
        "p": "pentacles",
        "s": "swords",
        "w": "wands",
    }

    if len(card_id) >= 3:
        suit_code = card_id[0]
        card_number = card_id[1:]

        if suit_code in suit_directories and card_number.isdigit():
            suit_dir = IMAGE_ROOT / "minor" / suit_directories[suit_code]

            for extension in (".png", ".jpg", ".jpeg", ".webp"):
                path = suit_dir / f"{int(card_number):02d}{extension}"
                if path.is_file():
                    return path

    # Major Arcana: numbered 01–22.
    if card_id.isdigit():
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            path = IMAGE_ROOT / "major" / f"{int(card_id):02d}{extension}"
            if path.is_file():
                return path

    # Fallback: match by card name.
    aliases = [
        str(card.get(key))
        for key in ("name", "display_name", "title", "card_name", "slug")
        if card.get(key) is not None
    ]

    files = _get_card_image_files()

    for alias in aliases:
        normalized = _normalize_image_name(alias)

        for filename in files:
            path = Path(filename)
            if _normalize_image_name(path.stem) == normalized:
                return path

    return None


def _show_card_image(
    card: dict,
    width: int = 220,
) -> bool:
    """Display a card image, rotating reversed cards."""
    path = _card_image_path(card)

    if path is None:
        return False

    try:
        with Image.open(path) as image:
            if card.get("reversed", False):
                image = image.rotate(180, expand=True)

            st.image(image.copy(), width=width)

        return True

    except (OSError, ValueError):
        logger.exception("Cannot display card image: %s", path)
        return False


def _render_cards(cards: list[dict[str, Any]]) -> None:
    if not cards:
        return
    columns = st.columns(min(3, len(cards)))
    for index, card in enumerate(cards):
        with columns[index % len(columns)]:
            _show_card_image(card)
            reversed_card = bool(card.get("reversed", False))
            orientation = _t("reversed") if reversed_card else _t("upright")
            st.markdown(f"**{_card_name(card)}**")
            st.caption(orientation)
            # Show useful card fields when the MCP payload provides them.
            for key, label in (
                ("short_meaning", "Short meaning"),
                ("meaning", "Meaning"),
                ("advice", "Advice"),
            ):
                value = card.get(key)
                if value and isinstance(value, str):
                    st.write(f"**{label}:** {value}")


# ---------------------------------------------------------------------------
# Card library (all cards of the deck)
# ---------------------------------------------------------------------------


def _card_id_sort_key(card_id: str) -> tuple[int, int, int]:
    """Sort order: Major Arcana first, then wands, cups, swords, pentacles."""
    card_id = card_id.lower()
    if card_id.isdigit():
        return (0, 0, int(card_id))
    suit_order = {"w": 0, "c": 1, "s": 2, "p": 3}
    number = card_id[1:]
    return (
        1,
        suit_order.get(card_id[:1], 9),
        int(number) if number.isdigit() else 0,
    )


def _load_library() -> list[dict[str, Any]]:
    cache: dict[str, list[dict[str, Any]]] = st.session_state.library_cache
    locale = st.session_state.locale or "default"

    if locale in cache:
        return cache[locale]

    sequence = _run_async(_mcp_call("generate_sequence"))

    # Preserve original card IDs exactly as returned by MCP.
    card_ids = {
        str(slot["id"])
        for slot in sequence.values()
        if isinstance(slot, dict) and "id" in slot
    }

    card_ids = sorted(card_ids, key=_card_id_sort_key)

    # Validate IDs before calling MCP.
    import re

    card_id_pattern = re.compile(
        r"^(?:0[1-9]|1[0-9]|2[0-2]|[cpsw](?:0[1-9]|1[0-4]))$"
    )

    invalid_ids = [card_id for card_id in card_ids if not card_id_pattern.fullmatch(card_id)]

    if invalid_ids:
        raise ValueError(f"Invalid card IDs returned by generate_sequence: {invalid_ids}")

    if len(card_ids) != 78:
        raise ValueError(f"Expected 78 unique cards, received {len(card_ids)}")

    result: list[dict[str, Any]] = []
    batch_size = 10

    for start in range(0, len(card_ids), batch_size):
        batch_ids = card_ids[start:start + batch_size]

        request = [
            {"id": card_id, "reversed": False}
            for card_id in batch_ids
        ]

        logger.debug(
            "Library request: %d cards, IDs=%s",
            len(batch_ids),
            batch_ids,
        )

        info = _run_async(
            _mcp_call("get_card_information", request)
        )

        batch_cards = info.get("cards", []) if isinstance(info, dict) else []

        if not isinstance(batch_cards, list):
            raise RuntimeError(
                f"Invalid get_card_information response for batch starting at {start}"
            )

        result.extend(batch_cards)

    cache[locale] = result
    return result


def _render_card_details(card: dict[str, Any]) -> None:
    """Large image plus all descriptive fields of one card."""
    image_col, text_col = st.columns([1, 2])
    with image_col:
        _show_card_image(card, width=280)
    with text_col:
        st.markdown(f"### {_card_name(card)}")
        for key, value in card.items():
            if key in HIDDEN_CARD_FIELDS or value in (None, "", [], {}):
                continue
            label = key.replace("_", " ").capitalize()
            if isinstance(value, str):
                st.markdown(f"**{label}:** {value}")
            elif isinstance(value, (list, tuple)):
                st.markdown(f"**{label}:**")
                for entry in value:
                    st.markdown(f"- {entry}")
            elif isinstance(value, dict):
                st.markdown(f"**{label}:**")
                for sub_key, sub_value in value.items():
                    st.markdown(
                        f"- *{str(sub_key).replace('_', ' ').capitalize()}:* {sub_value}"
                    )
            else:
                st.markdown(f"**{label}:** {value}")


def _open_card_details(card: dict[str, Any]) -> None:
    """Open a dialog with the card description (falls back to inline view)."""
    dialog = getattr(st, "dialog", None)
    if dialog is not None:
        dialog(_card_name(card), width="large")(_render_card_details)(card)
    else:
        # Older Streamlit: show the description at the top of the page.
        st.session_state.library_selected = card


def _render_library() -> None:
    st.title(_t("library_title"))
    st.caption(_t("library_subtitle"))

    try:
        with st.spinner(_t("library_loading")):
            cards = _load_library()
    except Exception as exc:
        logger.exception("Failed to load card library")
        st.error(_t("mcp_error", error=exc))
        return

    if not cards:
        st.warning(_t("library_empty"))
        return

    # Inline description (only used when st.dialog is unavailable).
    selected = st.session_state.library_selected
    if selected is not None and not hasattr(st, "dialog"):
        with st.container(border=True):
            _render_card_details(selected)
            if st.button(_t("library_close"), key="library_close"):
                st.session_state.library_selected = None
                st.rerun()

    st.caption(_t("library_count", count=len(cards)))

    for row_start in range(0, len(cards), LIBRARY_COLUMNS):
        row = cards[row_start : row_start + LIBRARY_COLUMNS]
        columns = st.columns(LIBRARY_COLUMNS)
        for offset, card in enumerate(row):
            with columns[offset]:
                shown = _show_card_image(card, width=150)
                if not shown and BACK_IMAGE_PATH.is_file():
                    st.image(str(BACK_IMAGE_PATH), width=150)
                button_key = f"library_card_{row_start + offset}_{card.get('id', '')}"
                if st.button(
                    _card_name(card),
                    key=button_key,
                    use_container_width=True,
                ):
                    _open_card_details(card)


# ---------------------------------------------------------------------------
# Reading flow
# ---------------------------------------------------------------------------


def _make_reading(question: str, positions: list[int]) -> None:
    config: AppConfig = st.session_state.config
    sequence = st.session_state.sequence
    drawn = [
        {
            "id": str(sequence[str(position)]["id"]),
            "reversed": bool(sequence[str(position)]["reversed"]),
        }
        for position in positions
    ]
    info = _run_async(_mcp_call("get_card_information", drawn))
    spread = info.get("cards", [])
    if not isinstance(spread, list):
        spread = []

    st.session_state.drawn = drawn
    st.session_state.spread_cards = spread
    st.session_state.question_text = question
    card_data_text = format_reading_info_for_llm(info, config.format)
    log_prompt_size_comparison(logger, info, card_data_text, label="reading")
    prompt = build_llm_prompt(
        config.llm.reading_prompt,
        question=question,
        card_data=card_data_text,
    )
    st.session_state.reading_text = _ask_llm(prompt)
    st.session_state.active_reading = True
    st.session_state.clarification_history = []


def _draw_clarification(position: int) -> None:
    config: AppConfig = st.session_state.config
    sequence = st.session_state.sequence
    position_id = str(position)
    slot = sequence.get(position_id)
    if not slot:
        st.error(_t("deck_not_ready"))
        return

    card = {
        "id": str(slot["id"]),
        "reversed": bool(slot["reversed"]),
    }
    if any(item["id"] == card["id"] and item["reversed"] == card["reversed"] for item in st.session_state.drawn):
        st.warning(_t("already_drawn"))
        return

    extra = _run_async(
        _mcp_call("get_additional_card", card, list(st.session_state.drawn))
    )
    if "card" in extra:
        st.session_state.drawn.append(card)

    card_data_text = format_clarification_for_llm(
        extra,
        config.format,
        drawn_cards=st.session_state.spread_cards,
    )
    log_prompt_size_comparison(logger, extra, card_data_text, label="clarification")
    prompt = build_llm_prompt(
        config.llm.clarification_prompt,
        card_data=card_data_text,
    )
    reply = _ask_llm(prompt)
    st.session_state.clarification_history.append(
        {"kind": "card", "position": position, "text": reply, "payload": extra}
    )
    st.session_state.clarification_selected_position = None


def _submit_followup(question: str) -> None:
    if not question.strip():
        return
    prompt = st.session_state.config.llm.follow_up_prompt.format(
        follow_up=question.strip()
    )
    reply = _ask_llm(prompt)
    st.session_state.clarification_history.append(
        {"kind": "question", "question": question.strip(), "text": reply}
    )


def _render_reading_page() -> None:
    st.title(_t("title"))
    st.caption(_t("subtitle"))

    with st.form("question_form"):
        question = st.text_area(
            _t("question"),
            value=st.session_state.question_text,
            placeholder=_t("question_placeholder"),
            height=90,
        )
        start = st.form_submit_button(
            _t("shuffle"),
            help=_t("shuffle_help"),
            type="primary",
            use_container_width=True,
        )

    if start:
        if not question.strip():
            st.warning(_t("no_question"))
        else:
            try:
                with st.spinner("Shuffling…"):
                    sequence = _run_async(_mcp_call("generate_sequence"))
                _reset_reading(reset_history=True)
                # Use fresh widget keys so selections from the previous deck
                # cannot leak into the newly shuffled deck.
                st.session_state.deck_version += 1
                st.session_state.sequence = sequence
                st.session_state.deck_ready = True
                st.session_state.question_text = question.strip()
                st.rerun()
            except Exception as exc:
                logger.exception("Failed to shuffle tarot deck")
                st.error(_t("mcp_error", error=exc))

    if st.session_state.deck_ready:
        _render_card_table_styles()

    if st.session_state.deck_ready and not st.session_state.active_reading:
        st.info(_t("deck_ready"))

        deck_size = st.session_state.config.bot.deck_size
        deck_version = st.session_state.deck_version
        selected_positions = set(st.session_state.selected_positions)
        st.subheader(_t("positions"))
        st.caption(_t("positions_help", max=deck_size))

        # Render the shuffled deck as five rows of 15 card backs (plus any
        # remaining cards in a final partial row, for a standard 78-card deck).
        for row_start in range(1, deck_size + 1, CARDS_PER_ROW):
            columns = st.columns(CARDS_PER_ROW, gap="small")
            row_end = min(row_start + CARDS_PER_ROW, deck_size + 1)

            for offset, position in enumerate(range(row_start, row_end)):
                with columns[offset]:
                    is_selected = position in selected_positions
                    if st.button(
                        _t("select_card", position=position),
                        key=f"card_pick_{deck_version}_{position}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                    ):
                        updated_positions = set(st.session_state.selected_positions)
                        if position in updated_positions:
                            updated_positions.remove(position)
                        else:
                            updated_positions.add(position)
                        st.session_state.selected_positions = sorted(updated_positions)
                        st.rerun()

        with st.form("draw_form"):
            draw = st.form_submit_button(
                _t("draw"),
                type="primary",
                use_container_width=True,
            )

        if draw:
            selected_positions = st.session_state.selected_positions
            if not selected_positions:
                st.warning(_t("no_positions"))
            else:
                try:
                    with st.spinner("Reading the cards…"):
                        _make_reading(
                            st.session_state.question_text,
                            selected_positions,
                        )
                    st.rerun()
                except Exception as exc:
                    logger.exception("Failed to generate tarot reading")
                    if isinstance(exc, LLMError):
                        st.error(_t("llm_error", error=exc))
                    else:
                        st.error(_t("mcp_error", error=exc))

    if st.session_state.active_reading:
        st.divider()
        st.subheader(_t("selected_cards"))
        _render_cards(st.session_state.spread_cards)

        st.subheader(_t("reading"))
        st.markdown(st.session_state.reading_text or _t("empty_reply"))

        st.divider()
        st.subheader(_t("clarification"))
        st.caption(_t("clarification_help"))
        deck_size = st.session_state.config.bot.deck_size
        deck_version = st.session_state.deck_version
        drawn_signatures = {
            (str(item["id"]), bool(item["reversed"]))
            for item in st.session_state.drawn
        }
        selected_position = st.session_state.clarification_selected_position

        # If the selected position has become unavailable, clear the stale selection.
        available_positions = []
        for position in range(1, deck_size + 1):
            slot = st.session_state.sequence.get(str(position))
            if not isinstance(slot, dict):
                continue
            signature = (str(slot["id"]), bool(slot["reversed"]))
            if signature not in drawn_signatures:
                available_positions.append(position)

        if selected_position not in available_positions:
            selected_position = None
            st.session_state.clarification_selected_position = None

        # Keep the original deck layout. Drawn cards are rendered face up and
        # are not buttons, while the remaining card backs can be selected.
        for row_start in range(1, deck_size + 1, CARDS_PER_ROW):
            columns = st.columns(CARDS_PER_ROW, gap="small")
            row_end = min(row_start + CARDS_PER_ROW, deck_size + 1)

            for offset, position in enumerate(range(row_start, row_end)):
                with columns[offset]:
                    slot = st.session_state.sequence.get(str(position))
                    if not isinstance(slot, dict):
                        st.empty()
                        continue

                    signature = (str(slot["id"]), bool(slot["reversed"]))
                    if signature in drawn_signatures:
                        face_card = {
                            "id": str(slot["id"]),
                            "reversed": bool(slot["reversed"]),
                        }
                        if not _show_card_image(face_card, width=60):
                            st.markdown(
                                "<div style='height:104px; display:flex; align-items:center; "
                                "justify-content:center; border:1px solid #8b806c; "
                                "border-radius:7px; font-size:10px; text-align:center;'>"
                                "Drawn</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        is_selected = position == selected_position
                        if st.button(
                            _t("select_card", position=position),
                            key=f"card_clarify_{deck_version}_{position}",
                            type="primary" if is_selected else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state.clarification_selected_position = (
                                None if is_selected else position
                            )
                            st.rerun()

        draw_extra = st.button(
            _t("draw_extra"),
            type="primary",
            use_container_width=True,
            disabled=selected_position is None,
        )
        if draw_extra and selected_position is not None:
            try:
                with st.spinner("Drawing a clarification card…"):
                    _draw_clarification(selected_position)
                st.rerun()
            except Exception as exc:
                logger.exception("Failed to draw clarification card")
                if isinstance(exc, LLMError):
                    st.error(_t("llm_error", error=exc))
                else:
                    st.error(_t("mcp_error", error=exc))

        if st.session_state.clarification_history:
            st.subheader(_t("followup_history"))

            for item in st.session_state.clarification_history:
                if item["kind"] == "card":
                    card = item["payload"].get("card", {})

                    st.markdown(
                        f"**{_t('drawn')} — {_card_name(card)}**"
                    )

                    # Display the additional card image and its information.
                    _render_cards([card])

                else:
                    st.markdown(f"**{item['question']}**")

                st.markdown(item["text"])

        with st.form("followup_form", clear_on_submit=True):
            followup = st.text_input(
                _t("followup"),
                placeholder=_t("followup_placeholder"),
            )
            send_followup = st.form_submit_button(_t("send"))
        if send_followup:
            try:
                with st.spinner("Thinking…"):
                    _submit_followup(followup)
                st.rerun()
            except Exception as exc:
                logger.exception("Follow-up failed")
                st.error(_t("llm_error", error=exc))

        if st.button(_t("new_reading"), use_container_width=True):
            _reset_reading(reset_history=True)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Tarot", page_icon="🔮", layout="wide")
    _init_state()

    with st.sidebar:
        selected_locale = st.selectbox(
            "Interface language",
            options=["en", "ru"],
            index=0 if st.session_state.locale != "ru" else 1,
            format_func=lambda value: "English" if value == "en" else "Русский",
        )
        if selected_locale != st.session_state.locale:
            st.session_state.locale = selected_locale
            st.rerun()

        st.radio(
            _t("mode"),
            options=["reading", "library"],
            format_func=lambda value: _t("mode_reading")
            if value == "reading"
            else _t("mode_library"),
            key="mode",
        )

    try:
        st.session_state.config = _load_config(st.session_state.locale)
    except Exception as exc:
        st.error(_t("config_error", error=exc))
        st.stop()

    if st.session_state.messages is None:
        st.session_state.messages = [
            {"role": "system", "content": st.session_state.config.llm.system_prompt}
        ]

    if st.session_state.mode == "library":
        _render_library()
    else:
        _render_reading_page()


if __name__ == "__main__":
    main()