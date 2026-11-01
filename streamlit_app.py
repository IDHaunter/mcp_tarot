"""Streamlit web interface for the Tarot MCP client.

Run from the project root:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

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
logger = logging.getLogger(__name__)

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
        "positions_help": "Choose distinct positions from 1 to {max}. Three cards are recommended.",
        "draw": "Draw cards and interpret",
        "new_reading": "Start a new reading",
        "reading": "Your reading",
        "selected_cards": "Cards in this spread",
        "clarification": "Clarify the reading",
        "clarification_help": "Choose another position to draw one additional card.",
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
        "positions_help": "Выберите разные позиции от 1 до {max}. Рекомендуется три карты.",
        "draw": "Вытянуть карты и получить толкование",
        "new_reading": "Начать новый расклад",
        "reading": "Ваше толкование",
        "selected_cards": "Карты расклада",
        "clarification": "Уточнить расклад",
        "clarification_help": "Выберите другую позицию, чтобы вытянуть дополнительную карту.",
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
    setup_logging(config.logging, base_dir=ROOT)
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
        "deck_ready": False,
        "active_reading": False,
        "locale": os.environ.get("TAROT_LOCALE", ""),
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


def _render_cards(cards: list[dict[str, Any]]) -> None:
    if not cards:
        return
    columns = st.columns(min(3, len(cards)))
    for index, card in enumerate(cards):
        with columns[index % len(columns)]:
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

    try:
        st.session_state.config = _load_config(st.session_state.locale)
    except Exception as exc:
        st.error(_t("config_error", error=exc))
        st.stop()

    if st.session_state.messages is None:
        st.session_state.messages = [
            {"role": "system", "content": st.session_state.config.llm.system_prompt}
        ]

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
                st.session_state.sequence = sequence
                st.session_state.deck_ready = True
                st.session_state.question_text = question.strip()
                st.rerun()
            except Exception as exc:
                logger.exception("Failed to shuffle tarot deck")
                st.error(_t("mcp_error", error=exc))

    if st.session_state.deck_ready and not st.session_state.active_reading:
        st.info(_t("deck_ready"))
        with st.form("draw_form"):
            selected_positions = st.multiselect(
                _t("positions"),
                options=list(range(1, st.session_state.config.bot.deck_size + 1)),
                default=st.session_state.selected_positions,
                format_func=_position_label,
                help=_t(
                    "positions_help",
                    max=st.session_state.config.bot.deck_size,
                ),
            )
            draw = st.form_submit_button(
                _t("draw"),
                type="primary",
                use_container_width=True,
            )
        st.session_state.selected_positions = selected_positions
        if draw:
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
        available_positions = [
            p
            for p in range(1, st.session_state.config.bot.deck_size + 1)
            if str(p) in st.session_state.sequence
            and not any(
                str(st.session_state.sequence[str(p)]["id"]) == item["id"]
                and bool(st.session_state.sequence[str(p)]["reversed"]) == bool(item["reversed"])
                for item in st.session_state.drawn
            )
        ]
        if available_positions:
            with st.form("clarification_form"):
                extra_position = st.selectbox(
                    _t("clarification_position"),
                    options=available_positions,
                    format_func=_position_label,
                )
                draw_extra = st.form_submit_button(_t("draw_extra"))
            if draw_extra:
                try:
                    with st.spinner("Drawing a clarification card…"):
                        _draw_clarification(extra_position)
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
                    st.markdown(f"**{_t('drawn')} — {_card_name(item['payload'].get('card', {}))}**")
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


if __name__ == "__main__":
    main()
