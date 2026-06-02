"""Load client configuration from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from server.locale_registry import default_locale_code, resolve_locale


class LLMConfig(BaseModel):
    """OpenAI-compatible chat API settings."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    timeout_seconds: float = 120.0
    system_prompt: str = ""
    reading_prompt: str = ""
    follow_up_prompt: str = ""
    clarification_prompt: str = ""


class MCPConfig(BaseModel):
    """MCP server subprocess settings."""

    command: str = "python"
    args: list[str] = Field(default_factory=lambda: ["-m", "server"])
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class FormatConfig(BaseModel):
    """Labels for compact LLM card text formatting."""

    card_label: str = "Card"
    clarification_card_label: str = "Clarification card"
    reversed_suffix: str = "reversed"
    label_meaning_for_today: str = "Today"
    label_card_advice: str = "Advice"
    label_short: str = "Short meaning"
    label_general: str = "General"
    label_in_love: str = "Love"
    label_in_situation: str = "Situation"
    interactions_heading: str = "Interactions"
    clarification_interactions_heading: str = "Interactions with spread"
    no_relation_text: str = "No relation text defined."

    def meaning_label_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return (json_key, label) pairs for card meaning lines."""
        return (
            ("meaning_for_today", self.label_meaning_for_today),
            ("card_advice", self.label_card_advice),
            ("short", self.label_short),
            ("general", self.label_general),
            ("in_love", self.label_in_love),
            ("in_situation", self.label_in_situation),
        )


class BotConfig(BaseModel):
    """Bot conversation settings and message templates."""

    recommended_spread_size: int = 3
    deck_size: int = 78
    quit_commands: list[str] = Field(
        default_factory=lambda: ["quit", "exit", "q"]
    )
    skip_commands: list[str] = Field(
        default_factory=lambda: ["no", "n", "skip"]
    )
    welcome_message: str = ""
    question_prompt: str = "\nYour question: "
    empty_question_message: str = "Please enter a question."
    goodbye_message: str = "Goodbye."
    select_cards_prompt: str = ""
    positions_prompt: str = "Positions: "
    invalid_positions_message: str = ""
    clarification_prompt: str = ""
    clarification_input_prompt: str = "\n{clarification}\n> "
    new_topic_prompt: str = ""
    new_topic_input_prompt: str = "\n{new_topic}\n> "
    no_active_reading_message: str = ""
    invalid_position_message: str = ""
    draw_card_error_message: str = "Could not draw card: {error}"
    llm_error_message: str = ""


class LoggingConfig(BaseModel):
    """Client file logging settings (stdlib logging levels)."""

    level: str = "INFO"
    file: str = "logs/client.log"


class AppConfig(BaseModel):
    """Root application configuration."""

    locale: str | None = None
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    format: FormatConfig = Field(default_factory=FormatConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file into a dict."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    path: str | Path,
    *,
    project_root: Path | None = None,
    locale: str | None = None,
) -> tuple[AppConfig, str]:
    """Load configuration and resolve active locale.

    Args:
        path: Path to base ``client.yaml``.
        project_root: Project root for locale files and manifest.
        locale: Optional locale override (CLI / env).

    Returns:
        Tuple of (config, active locale code).
    """
    root = project_root or Path(__file__).resolve().parent.parent
    raw = _read_yaml(Path(path))

    requested = locale or raw.get("locale") or None
    if isinstance(requested, str):
        requested = requested.strip() or None

    active_locale = resolve_locale(requested)

    locale_path = root / "config" / "locales" / f"{active_locale}.yaml"
    locale_raw = _read_yaml(locale_path)
    if not locale_raw:
        raise FileNotFoundError(
            f"Locale config not found for {active_locale!r}: {locale_path}"
        )

    merged = _deep_merge(raw, locale_raw)
    merged["locale"] = active_locale
    return AppConfig.model_validate(merged), active_locale


def default_manifest_locale() -> str:
    """Return default locale from server manifest (no env)."""
    return default_locale_code()
