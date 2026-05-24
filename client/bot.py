"""Interactive tarot bot conversation flow."""

from __future__ import annotations

import json
import re
from typing import Any

from client.config import AppConfig
from client.llm import LLMClient
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
) -> list[str]:
    """Keep only valid, in-range deck positions."""
    valid: list[str] = []
    for pos in positions:
        if pos in sequence and 1 <= int(pos) <= 78:
            valid.append(pos)
    return valid


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
        self._mcp = mcp
        self._llm = llm
        self._sequence: dict[str, dict[str, str | bool]] = {}
        self._drawn: list[dict[str, str | bool]] = []
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": config.llm.system_prompt},
        ]

    def _ask_llm(self, user_content: str) -> str:
        """Append user message, call LLM, store assistant reply."""
        self._messages.append({"role": "user", "content": user_content})
        reply = self._llm.chat(self._messages)
        self._messages.append({"role": "assistant", "content": reply})
        return reply

    async def run(self) -> None:
        """Run the main conversation loop until the user quits."""
        print(self._config.bot.welcome_message)

        while True:
            question = _read_line("\nYour question: ")
            if not question:
                print("Please enter a question.")
                continue
            if question.lower() in {"quit", "exit", "q"}:
                print("Goodbye.")
                return

            await self._run_reading(question)

            while True:
                follow = _read_line(f"\n{self._config.bot.clarification_prompt}\n> ")
                if follow.lower() in {"no", "n", "skip"}:
                    break
                if follow.lower() in {"quit", "exit", "q"}:
                    print("Goodbye.")
                    return

                if re.fullmatch(r"\d+", follow):
                    await self._draw_clarification(follow)
                    continue

                reply = self._ask_llm(
                    f"The user asks about their reading: {follow}\n"
                    "Answer using the card data already discussed."
                )
                print(f"\n{reply}")

            new_topic = _read_line(f"\n{self._config.bot.new_topic_prompt}\n> ")
            if new_topic.lower() in {"quit", "exit", "q"}:
                print("Goodbye.")
                return
            if new_topic:
                self._messages = [
                    {"role": "system", "content": self._config.llm.system_prompt},
                ]
                await self._run_reading(new_topic)

    async def _run_reading(self, question: str) -> None:
        """Execute one full spread for a question."""
        sequence = await self._mcp.generate_sequence()

        prompt = self._config.bot.select_cards_prompt.format(
            count="different",
            recommended=self._config.bot.recommended_spread_size,
        )
        print(f"\n{prompt}")

        drawn_cards: list[dict[str, str | bool]] = []
        while not drawn_cards:
            selection = _read_line("Positions: ")
            positions = _validate_positions(_parse_positions(selection), sequence)
            if not positions:
                print("Enter valid position numbers between 1 and 78.")
                continue
            drawn_cards = _cards_from_positions(positions, sequence)

        info = await self._mcp.get_card_information(drawn_cards)
        self._sequence = sequence
        self._drawn = drawn_cards

        context = (
            f"The user's question: {question}\n\n"
            f"Card data (JSON):\n{json.dumps(info, ensure_ascii=False, indent=2)}\n\n"
            "Give a cohesive tarot reading for this question using these cards. "
            "Do not reveal internal deck positions or the full shuffled deck. "
            "Refer to cards by name and upright/reversed orientation."
        )
        reading = self._ask_llm(context)
        print(f"\n{reading}")

    async def _draw_clarification(self, position_id: str) -> None:
        """Draw one more card from the stored sequence."""
        sequence = self._sequence
        drawn = list(self._drawn)

        if not sequence:
            print("No active reading. Start with a new question.")
            return

        if position_id not in sequence:
            print("Invalid position. Choose a number from 1 to 78.")
            return

        try:
            extra = await self._mcp.get_additional_card(
                position_id, sequence, drawn
            )
        except RuntimeError as exc:
            print(f"Could not draw card: {exc}")
            return

        if "card" in extra:
            slot = sequence[position_id]
            drawn.append(
                {"id": str(slot["id"]), "reversed": bool(slot["reversed"])}
            )
            self._drawn = drawn

        context = (
            "The user requested a clarification card. "
            f"Additional draw data (JSON):\n"
            f"{json.dumps(extra, ensure_ascii=False, indent=2)}\n\n"
            "Discuss how this card clarifies the reading. "
            "Do not mention deck position numbers."
        )
        reply = self._ask_llm(context)
        print(f"\n{reply}")
