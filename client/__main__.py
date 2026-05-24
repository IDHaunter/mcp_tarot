"""Entry point for the tarot interactive client."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from client.bot import TarotBot
from client.config import load_config
from client.llm import LLMClient
from client.mcp_session import open_tarot_mcp


_PLACEHOLDER_LLM_HOSTS = frozenset({"my-llm-provider.com", "example.com"})


def _warn_placeholder_llm_url(base_url: str) -> None:
    """Print a warning when base_url still uses a documentation placeholder."""
    from urllib.parse import urlparse

    host = urlparse(base_url).hostname or ""
    if host in _PLACEHOLDER_LLM_HOSTS:
        print(
            "Warning: llm.base_url looks like a placeholder "
            f"({base_url}).\n"
            "Set a real API URL in config/client.yaml or LLM_BASE_URL.\n"
        )


def _default_config_path() -> Path:
    """Resolve default config path next to project root."""
    root = Path(__file__).resolve().parent.parent
    return root / "config" / "client.yaml"


def main() -> None:
    """Parse arguments and run the bot."""
    parser = argparse.ArgumentParser(description="Tarot MCP interactive client")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to YAML configuration file",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if base_url_override := os.environ.get("LLM_BASE_URL"):
        config.llm.base_url = base_url_override

    if not config.llm.api_key:
        config.llm.api_key = os.environ.get("OPENAI_API_KEY", "")

    _warn_placeholder_llm_url(config.llm.base_url)

    project_root = Path(__file__).resolve().parent.parent
    if config.mcp.cwd is None:
        config.mcp.cwd = str(project_root)
    if config.mcp.command == "python":
        config.mcp.command = sys.executable

    async def _run() -> None:
        llm = LLMClient(config.llm)
        async with open_tarot_mcp(config.mcp) as mcp_client:
            bot = TarotBot(config, mcp_client, llm)
            await bot.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nGoodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
