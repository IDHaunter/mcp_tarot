"""Interactive tarot bot conversation flow."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from client.config import AppConfig, BotConfig
from client.llm import LLMClient, LLMError
from client.mcp_session import TarotMCPClient


def _read_line(prompt: str = "") -> str:
    """Read one line of user input."""
    if prompt:
        print(prompt, end="", flush=True)
    return input().strip()


def _parse_positions(text: str) -> list[str]:
    """Extract unique position numbers from user input."""
    numbers = re.findall(r"\d+", text)
    seen: set[str] = set()
    positions: list[str] = []
    for num in numbers:
        if num not in seen:
            seen.add(num)
            positions.append(num)
    return positions


def _validate_positions(
    positions: list[str],
    sequence: dict[str, dict[str, str | bool]],
    deck_max: int,
) -> list[str]:
    """Keep only valid, in-range deck positions."""
    valid: list[str] = []
    for pos in positions:
        if pos in sequence and 1 <= int(pos) <= deck_max:
            valid.append(pos)
    return valid


def _command_hint(commands: list[str]) -> str:
    """Format command tokens for display in user prompts."""
    return ", ".join(commands)


def _cards_from_positions(
    positions: list[str],
    sequence: dict[str, dict[str, str | bool]],
) -> list[dict[str, str | bool]]:
    """Map deck positions to card id and reversed flag."""
    cards: list[dict[str, str | bool]] = []
    for pos in positions:
        slot = sequence[pos]
        cards.append({"id": str(slot["id"]), "reversed": bool(slot["reversed"])})
    return cards


class TarotBot:
    """Console bot orchestrating MCP tools and LLM interpretation."""

    def __init__(
        self,
        config: AppConfig,
        mcp: TarotMCPClient,
        llm: LLMClient,
    ) -> None:
        self._config = config
        self._bot: BotConfig = config.bot
        self._mcp = mcp
        self._llm = llm
        self._sequence: dict[str, dict[str, str | bool]] = {}
        self._drawn: list[dict[str, str | bool]] = []
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": config.llm.system_prompt},
        ]
        self._quit_commands = {c.lower() for c in self._bot.quit_commands}
        self._skip_commands = {c.lower() for c in self._bot.skip_commands}

    def _deck_template(self) -> dict[str, int]:
        """Common format placeholders for deck-bound messages."""
        return {
            "deck_max": self._bot.deck_size,
            "recommended": self._bot.recommended_spread_size,
        }

    def _bot_template(self) -> dict[str, int | str]:
        """Placeholders for bot messages (deck + command hints)."""
        template = dict(self._deck_template())
        template["skip_hint"] = _command_hint(self._bot.skip_commands)
        template["quit_hint"] = _command_hint(self._bot.quit_commands)
        return template

    def _is_quit(self, text: str) -> bool:
        return text.lower() in self._quit_commands

    def _is_skip(self, text: str) -> bool:
        return text.lower() in self._skip_commands

    async def _ask_llm(self, user_content: str) -> str | None:
        """Append user message, call LLM, store assistant reply."""
        self._messages.append({"role": "user", "content": user_content})
        try:
            reply = await asyncio.to_thread(self._llm.chat, self._messages)
        except LLMError as exc:
            self._messages.pop()
            print(
                self._bot.llm_error_message.format(
                    error=exc,
                    base_url=self._llm.base_url,
                )
            )
            return None

        self._messages.append({"role": "assistant", "content": reply})
        return reply

    async def run(self) -> None:
        """Run the main conversation loop until the user quits."""
        print(self._bot.welcome_message)

        while True:
            question = _read_line(self._bot.question_prompt)
            if not question:
                print(self._bot.empty_question_message)
                continue
            if self._is_quit(question):
                print(self._bot.goodbye_message)
                return

            await self._run_reading(question)

            while True:
                bot_tpl = self._bot_template()
                follow_prompt = self._bot.clarification_input_prompt.format(
                    clarification=self._bot.clarification_prompt.format(**bot_tpl),
                )
                follow = _read_line(follow_prompt)
                if self._is_skip(follow):
                    break
                if self._is_quit(follow):
                    print(self._bot.goodbye_message)
                    return

                if re.fullmatch(r"\d+", follow):
                    await self._draw_clarification(follow)
                    continue

                reply = await self._ask_llm(
                    self._config.llm.follow_up_prompt.format(follow_up=follow)
                )
                if reply:
                    print(f"\n{reply}")

            bot_tpl = self._bot_template()
            new_topic_prompt = self._bot.new_topic_input_prompt.format(
                new_topic=self._bot.new_topic_prompt.format(**bot_tpl),
            )
            new_topic = _read_line(new_topic_prompt)
            if self._is_quit(new_topic):
                print(self._bot.goodbye_message)
                return
            if self._is_skip(new_topic):
                continue
            if new_topic:
                self._messages = [
                    {"role": "system", "content": self._config.llm.system_prompt},
                ]
                await self._run_reading(new_topic)

    async def _run_reading(self, question: str) -> None:
        """Execute one full spread for a question."""
        sequence = await self._mcp.generate_sequence()

        prompt = self._bot.select_cards_prompt.format(**self._bot_template())
        print(f"\n{prompt}")

        drawn_cards: list[dict[str, str | bool]] = []
        deck_tpl = self._deck_template()
        while not drawn_cards:
            selection = _read_line(self._bot.positions_prompt)
            positions = _validate_positions(
                _parse_positions(selection), sequence, self._bot.deck_size
            )
            if not positions:
                print(self._bot.invalid_positions_message.format(**deck_tpl))
                continue
            drawn_cards = _cards_from_positions(positions, sequence)

        info = await self._mcp.get_card_information(drawn_cards)
        self._sequence = sequence
        self._drawn = drawn_cards

        context = self._config.llm.reading_prompt.format(
            question=question,
            card_data=json.dumps(info, ensure_ascii=False, indent=2),
        )
        reading = await self._ask_llm(context)
        if reading:
            print(f"\n{reading}")

    async def _draw_clarification(self, position_id: str) -> None:
        """Draw one more card from the stored sequence."""
        sequence = self._sequence
        drawn = list(self._drawn)
        deck_tpl = self._deck_template()

        if not sequence:
            print(self._bot.no_active_reading_message)
            return

        if position_id not in sequence:
            print(self._bot.invalid_position_message.format(**deck_tpl))
            return

        try:
            extra = await self._mcp.get_additional_card(
                position_id, sequence, drawn
            )
        except RuntimeError as exc:
            print(
                self._bot.draw_card_error_message.format(error=exc)
            )
            return

        if "card" in extra:
            slot = sequence[position_id]
            drawn.append(
                {"id": str(slot["id"]), "reversed": bool(slot["reversed"])}
            )
            self._drawn = drawn

        context = self._config.llm.clarification_prompt.format(
            card_data=json.dumps(extra, ensure_ascii=False, indent=2),
        )
        reply = await self._ask_llm(context)
        if reply:
            print(f"\n{reply}")
