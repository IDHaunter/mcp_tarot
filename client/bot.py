"""Interactive tarot bot conversation flow."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from client.config import AppConfig, BotConfig
from client.llm import LLMClient, LLMError
from client.llm_format import (
    build_llm_prompt,
    format_clarification_for_llm,
    format_reading_info_for_llm,
    log_prompt_size_comparison,
)
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

        # Cards already drawn in current reading (id + reversed only)
        self._drawn: list[dict[str, str | bool]] = []

        # Full MCP card payloads for the active spread (includes names)
        self._spread_cards: list[dict[str, Any]] = []

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

        logger.debug(
            "LLM dialogue turn: history_messages=%d user_chars=%d",
            len(self._messages),
            len(user_content),
        )
        try:
            # Execute blocking LLM call in worker thread
            # to avoid blocking asyncio event loop
            reply = await asyncio.to_thread(
                self._llm.chat,
                self._messages,
            )

        except LLMError as exc:
            logger.warning("LLM dialogue turn failed: %s", exc)
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

        logger.debug("LLM dialogue turn completed")
        return reply

    async def run(self) -> None:
        """Run the main conversation loop until the user quits."""

        logger.info("Bot session started")
        # Display greeting message
        print(self._bot.welcome_message)

        while True:
            # Ask user for tarot question
            question = _read_line(
                self._bot.question_prompt
            )

            # Reject empty input
            if not question:
                logger.debug("User submitted empty question")
                print(self._bot.empty_question_message)
                continue

            # Exit application if user entered quit command
            if self._is_quit(question):
                logger.info("User quit from question prompt")
                print(self._bot.goodbye_message)
                return

            logger.info("New reading question received (%d chars)", len(question))
            logger.debug("User question: %s", question)
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
                logger.debug("Clarification input: %r", follow)

                # Skip clarification phase
                if self._is_skip(follow):
                    logger.debug("User skipped clarification loop")
                    break

                # Exit application
                if self._is_quit(follow):
                    logger.info("User quit from clarification prompt")
                    print(self._bot.goodbye_message)
                    return

                # If user entered only a number,
                # interpret it as request for extra card
                if re.fullmatch(r"\d+", follow):
                    logger.debug("User requested clarification card at %s", follow)
                    await self._draw_clarification(follow)
                    continue

                logger.debug("User follow-up question (%d chars)", len(follow))
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
            logger.debug("New topic input: %r", new_topic)

            # Exit application
            if self._is_quit(new_topic):
                logger.info("User quit from new-topic prompt")
                print(self._bot.goodbye_message)
                return

            # Restart loop without creating new reading
            if self._is_skip(new_topic):
                logger.debug("User returned to main question loop")
                continue

            # Start completely new conversation context
            if new_topic:
                logger.info("Starting new topic reading (%d chars)", len(new_topic))
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

        logger.info("Reading flow started")
        # Generate randomized tarot sequence
        sequence = await self._mcp.generate_sequence()
        logger.debug("Deck sequence generated (78 positions)")

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
                logger.debug("Invalid card positions input: %r", selection)
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
            logger.info(
                "Cards selected: positions=%s cards=%s",
                positions,
                drawn_cards,
            )

        # Request detailed information for selected cards
        info = await self._mcp.get_card_information(
            drawn_cards
        )
        logger.debug("Card information loaded for spread")

        # Save current reading state
        self._sequence = sequence
        self._drawn = drawn_cards
        spread = info.get("cards", [])
        self._spread_cards = spread if isinstance(spread, list) else []

        card_data_text = format_reading_info_for_llm(
            info, self._config.format
        )
        log_prompt_size_comparison(
            logger, info, card_data_text, label="reading"
        )
        context = build_llm_prompt(
            self._config.llm.reading_prompt,
            question=question,
            card_data=card_data_text,
        )

        # Generate interpretation
        reading = await self._ask_llm(context)

        if reading:
            logger.info("Reading interpretation delivered to user")
            print(f"\n{reading}")
        else:
            logger.warning("Reading interpretation not delivered (LLM error)")

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
            logger.warning("Clarification requested without active reading")
            print(self._bot.no_active_reading_message)
            return

        # Validate requested position
        if position_id not in sequence:
            logger.debug("Invalid clarification position: %s", position_id)
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
            logger.warning("Additional card draw failed: %s", exc)
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
            logger.info(
                "Clarification card drawn at position %s: %s",
                position_id,
                extra.get("card", {}).get("id"),
            )
            slot = sequence[position_id]

            drawn.append({
                "id": str(slot["id"]),
                "reversed": bool(slot["reversed"]),
            })

            self._drawn = drawn

        card_data_text = format_clarification_for_llm(
            extra,
            self._config.format,
            drawn_cards=self._spread_cards,
        )
        log_prompt_size_comparison(
            logger, extra, card_data_text, label="clarification"
        )
        context = build_llm_prompt(
            self._config.llm.clarification_prompt,
            card_data=card_data_text,
        )

        # Generate clarification interpretation
        reply = await self._ask_llm(context)

        if reply:
            logger.info("Clarification interpretation delivered to user")
            print(f"\n{reply}")
        else:
            logger.warning(
                "Clarification interpretation not delivered (LLM error)"
            )