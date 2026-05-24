"""Load client configuration from YAML."""

from __future__ import annotations

from pathlib import Path

from typing import Any

import yaml

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """OpenAI-compatible chat API settings."""

    # Base URL of the LLM API endpoint.
    # Can point to:
    # - OpenAI
    # - local Ollama proxy
    # - LiteLLM gateway
    # - any OpenAI-compatible provider
    base_url: str = "https://api.openai.com/v1"

    # API key used for authentication
    api_key: str = ""

    # Default model name
    model: str = "gpt-4o-mini"

    # Controls randomness of model responses:
    # lower -> more deterministic
    # higher -> more creative
    temperature: float = 0.7

    # Maximum request timeout in seconds
    timeout_seconds: float = 120.0

    # System prompt sent to the LLM before conversation.
    # Defines assistant personality and behavior rules.
    system_prompt: str = (
        "You are a thoughtful tarot reader. Interpret cards with empathy and "
        "clarity. Connect card meanings to the user's question. Use the provided "
        "card data and pair relations; do not invent card names or positions the "
        "user did not draw. Keep a warm, conversational tone."
    )


class MCPConfig(BaseModel):
    """MCP server subprocess settings."""

    # Executable used to launch MCP server.
    # Usually:
    # - python
    # - python3
    # - full path to interpreter
    command: str = "python"

    # Arguments passed to subprocess.
    #
    # default_factory is used instead of:
    # args: list[str] = ["-m", "server"]
    #
    # because mutable defaults should not be shared
    # between model instances.
    args: list[str] = Field(default_factory=lambda: ["-m", "server"])

    # Working directory for MCP subprocess.
    # If None, current process directory is used.
    cwd: str | None = None

    # Additional environment variables passed
    # to the subprocess.
    env: dict[str, str] = Field(default_factory=dict)


class BotConfig(BaseModel):
    """Bot conversation settings."""

    # Recommended number of cards for standard reading
    recommended_spread_size: int = 3

    # Initial greeting shown to user
    welcome_message: str = (
        "Welcome to the Tarot reading bot.\n\n"
        "You can ask a specific question and receive guidance through the tarot "
        "cards. When you are ready, type your question."
    )

    # Prompt asking user to choose card positions
    #
    # {count} and {recommended} are placeholders
    # inserted dynamically via str.format()
    select_cards_prompt: str = (
        "The deck is shuffled. Please choose {count} different card positions "
        "from the deck (numbers 1–78), separated by commas.\n"
        "For example: 3, 17, 42\n"
        "It is recommended to pick {recommended} cards for your spread."
    )

    # Prompt for optional clarification card
    clarification_prompt: str = (
        "Would you like to draw one more card from the deck for clarification? "
        "If yes, enter a single position number (1–78). "
        "If not, type 'no' or ask a follow-up question about your reading."
    )

    # Prompt shown after reading is complete
    new_topic_prompt: str = (
        "Would you like a reading on a different topic? "
        "Type your new question, or 'quit' to exit."
    )


class AppConfig(BaseModel):
    """Root application configuration."""

    # default_factory creates a fresh LLMConfig instance
    # if section is missing in YAML
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # MCP server configuration
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    # Bot dialogue configuration
    bot: BotConfig = Field(default_factory=BotConfig)


def load_config(path: str | Path) -> AppConfig:
    """Load configuration from a YAML file.

    Args:
        path: Path to YAML config.

    Returns:
        Parsed ``AppConfig`` instance.
    """

    # Convert input into Path object
    config_path = Path(path)

    # Default empty raw configuration.
    raw: dict[str, Any] = {}

    # Check that config file exists
    # and is a regular file
    if config_path.is_file():

        # Open YAML file using UTF-8 encoding
        with config_path.open(encoding="utf-8") as handle:

            # safe_load prevents execution of arbitrary
            loaded = yaml.safe_load(handle)

            # Ensure loaded YAML root is a dictionary.
            if isinstance(loaded, dict):
                raw = loaded

    # Validate and construct AppConfig object.
    return AppConfig.model_validate(raw)