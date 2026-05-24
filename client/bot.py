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
    # Print prompt without a newline to keep input on the same line
    if prompt:
        print(prompt, end="", flush=True)

    # Read input from console and remove surrounding spaces
    return input().strip()


def _parse_positions(text: str) -> list[str]:
    """Extract unique position numbers from user input."""
    # Find all numeric substrings in the input text
    numbers = re.findall(r"\d+", text)

    # Preserve order while removing duplicates
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
        # Position must exist in generated sequence
        # and be inside allowed deck range
        if pos in sequence and 1 <= int(pos) <= deck_max:
            valid.append(pos)

    return valid


def _command_hint(commands: list[str]) -> str:
    """Format command tokens for display in user prompts."""
    # Convert command list into human-readable string
    return ", ".join(commands)


def _cards_from_positions(
    positions: list[str],
    sequence: dict[str, dict[str, str | bool]],
) -> list[dict[str, str | bool]]:
    """Map deck positions to card id and reversed flag."""
    cards: list[dict[str, str | bool]] = []

    for pos in positions:
        # Get generated card data for selected position
        slot = sequence[pos]

        # Build compact card descriptor
        cards.append({
            "id": str(slot["id"]),
            "reversed": bool(slot["reversed"]),
        })

    return cards


class TarotBot:
    """Console bot orchestrating MCP tools and LLM interpretation."""

    def __init__(
        self,
        config: AppConfig,
        mcp: TarotMCPClient,
        llm: LLMClient,
    ) -> None:
        # Store application configuration
        self._config = config

        # Shortcut to bot-specific configuration section
        self._bot: BotConfig = config.bot

        # MCP client used for tarot logic and card operations
        self._mcp = mcp

        # LLM client used for generating interpretations
        self._llm = llm

        # Current generated deck sequence
        self._sequence: dict[str, dict[str, str | bool]] = {}

        # Cards already drawn in current reading
        self._drawn: list[dict[str, str | bool]] = []

        # Full LLM conversation history
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": config.llm.system_prompt},
        ]

        # Pre-normalized command sets for fast comparisons
        self._quit_commands = {
            c.lower() for c in self._bot.quit_commands
        }
        self._skip_commands = {
            c.lower() for c in self._bot.skip_commands
        }

    def _deck_template(self) -> dict[str, int]:
        """Common format placeholders for deck-bound messages."""
        # Shared placeholders used in prompt formatting
        return {
            "deck_max": self._bot.deck_size,
            "recommended": self._bot.recommended_spread_size,
        }

    def _bot_template(self) -> dict[str, int | str]:
        """Placeholders for bot messages (deck + command hints)."""
        # Start with generic deck-related placeholders
        template = dict(self._deck_template())

        # Add command hints for prompts
        template["skip_hint"] = _command_hint(
            self._bot.skip_commands
        )
        template["quit_hint"] = _command_hint(
            self._bot.quit_commands
        )

        return template

    def _is_quit(self, text: str) -> bool:
        # Check whether user entered quit command
        return text.lower() in self._quit_commands

    def _is_skip(self, text: str) -> bool:
        # Check whether user entered skip command
        return text.lower() in self._skip_commands

    async def _ask_llm(self, user_content: str) -> str | None:
        """Append user message, call LLM, store assistant reply."""

        # Save user message into conversation history
        self._messages.append({
            "role": "user",
            "content": user_content,
        })

        try:
            # Execute blocking LLM call in worker thread
            # to avoid blocking asyncio event loop
            reply = await asyncio.to_thread(
                self._llm.chat,
                self._messages,
            )

        except LLMError as exc:
            # Remove failed user message from history
            self._messages.pop()

            # Display formatted error information
            print(
                self._bot.llm_error_message.format(
                    error=exc,
                    base_url=self._llm.base_url,
                )
            )

            return None

        # Save assistant response into conversation history
        self._messages.append({
            "role": "assistant",
            "content": reply,
        })

        return reply

    async def run(self) -> None:
        """Run the main conversation loop until the user quits."""

        # Display greeting message
        print(self._bot.welcome_message)

        while True:
            # Ask user for tarot question
            question = _read_line(
                self._bot.question_prompt
            )

            # Reject empty input
            if not question:
                print(self._bot.empty_question_message)
                continue

            # Exit application if user entered quit command
            if self._is_quit(question):
                print(self._bot.goodbye_message)
                return

            # Execute tarot reading flow
            await self._run_reading(question)

            # Clarification loop after initial reading
            while True:
                bot_tpl = self._bot_template()

                # Build clarification prompt dynamically
                follow_prompt = (
                    self._bot.clarification_input_prompt.format(
                        clarification=(
                            self._bot.clarification_prompt.format(
                                **bot_tpl
                            )
                        ),
                    )
                )

                follow = _read_line(follow_prompt)

                # Skip clarification phase
                if self._is_skip(follow):
                    break

                # Exit application
                if self._is_quit(follow):
                    print(self._bot.goodbye_message)
                    return

                # If user entered only a number,
                # interpret it as request for extra card
                if re.fullmatch(r"\d+", follow):
                    await self._draw_clarification(follow)
                    continue

                # Send free-text clarification request to LLM
                reply = await self._ask_llm(
                    self._config.llm.follow_up_prompt.format(
                        follow_up=follow
                    )
                )

                if reply:
                    print(f"\n{reply}")

            bot_tpl = self._bot_template()

            # Ask whether user wants a new reading/topic
            new_topic_prompt = (
                self._bot.new_topic_input_prompt.format(
                    new_topic=(
                        self._bot.new_topic_prompt.format(
                            **bot_tpl
                        )
                    ),
                )
            )

            new_topic = _read_line(new_topic_prompt)

            # Exit application
            if self._is_quit(new_topic):
                print(self._bot.goodbye_message)
                return

            # Restart loop without creating new reading
            if self._is_skip(new_topic):
                continue

            # Start completely new conversation context
            if new_topic:
                self._messages = [
                    {
                        "role": "system",
                        "content": (
                            self._config.llm.system_prompt
                        ),
                    },
                ]

                await self._run_reading(new_topic)

    async def _run_reading(self, question: str) -> None:
        """Execute one full spread for a question."""

        # Generate randomized tarot sequence
        sequence = await self._mcp.generate_sequence()

        # Display card selection instructions
        prompt = self._bot.select_cards_prompt.format(
            **self._bot_template()
        )

        print(f"\n{prompt}")

        drawn_cards: list[dict[str, str | bool]] = []
        deck_tpl = self._deck_template()

        # Keep asking until valid card positions are selected
        while not drawn_cards:
            selection = _read_line(
                self._bot.positions_prompt
            )

            # Parse and validate selected positions
            positions = _validate_positions(
                _parse_positions(selection),
                sequence,
                self._bot.deck_size,
            )

            if not positions:
                print(
                    self._bot.invalid_positions_message.format(
                        **deck_tpl
                    )
                )
                continue

            # Convert positions into actual card descriptors
            drawn_cards = _cards_from_positions(
                positions,
                sequence,
            )

        # Request detailed information for selected cards
        info = await self._mcp.get_card_information(
            drawn_cards
        )

        # Save current reading state
        self._sequence = sequence
        self._drawn = drawn_cards

        # Build LLM prompt with user question and card data
        context = self._config.llm.reading_prompt.format(
            question=question,
            card_data=json.dumps(
                info,
                ensure_ascii=False,
                indent=2,
            ),
        )

        # Generate interpretation
        reading = await self._ask_llm(context)

        if reading:
            print(f"\n{reading}")

    async def _draw_clarification(
        self,
        position_id: str,
    ) -> None:
        """Draw one more card from the stored sequence."""

        # Work with local copies/current state
        sequence = self._sequence
        drawn = list(self._drawn)
        deck_tpl = self._deck_template()

        # Clarification is impossible without active reading
        if not sequence:
            print(self._bot.no_active_reading_message)
            return

        # Validate requested position
        if position_id not in sequence:
            print(
                self._bot.invalid_position_message.format(
                    **deck_tpl
                )
            )
            return

        try:
            # Request additional clarification card
            extra = await self._mcp.get_additional_card(
                position_id,
                sequence,
                drawn,
            )

        except RuntimeError as exc:
            # Display MCP/tool-related error
            print(
                self._bot.draw_card_error_message.format(
                    error=exc
                )
            )
            return

        # If a new card was successfully drawn,
        # add it to stored reading state
        if "card" in extra:
            slot = sequence[position_id]

            drawn.append({
                "id": str(slot["id"]),
                "reversed": bool(slot["reversed"]),
            })

            self._drawn = drawn

        # Build clarification request for LLM
        context = self._config.llm.clarification_prompt.format(
            card_data=json.dumps(
                extra,
                ensure_ascii=False,
                indent=2,
            ),
        )

        # Generate clarification interpretation
        reply = await self._ask_llm(context)

        if reply:
            print(f"\n{reply}")