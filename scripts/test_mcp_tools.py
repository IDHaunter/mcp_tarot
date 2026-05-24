"""Quick smoke test for MCP tarot tools."""

import asyncio
import json
import sys
from pathlib import Path

# Resolve project root directory:
# tests/smoke_test.py -> parent -> tests -> parent -> project root
ROOT = Path(__file__).resolve().parent.parent

# Add project root to PYTHONPATH so local modules can be imported
sys.path.insert(0, str(ROOT))

from client.config import MCPConfig
from client.mcp_session import open_tarot_mcp


async def main() -> None:
    # Create MCP client configuration.
    # sys.executable ensures the same Python interpreter is used.
    # cwd defines the working directory for the MCP subprocess.
    config = MCPConfig(command=sys.executable, cwd=str(ROOT))

    # Open async MCP session.
    # The context manager is responsible for startup and cleanup.
    async with open_tarot_mcp(config) as mcp:

        # Generate a full tarot deck sequence
        seq = await mcp.generate_sequence()

        # Tarot deck must contain exactly 78 cards
        assert len(seq) == 78

        # Take first two cards from generated sequence
        # and normalize field types for API compatibility
        cards = [
            {
                "id": str(seq["1"]["id"]),
                "reversed": bool(seq["1"]["reversed"]),
            },
            {
                "id": str(seq["2"]["id"]),
                "reversed": bool(seq["2"]["reversed"]),
            },
        ]

        # Request detailed information for selected cards
        info = await mcp.get_card_information(cards)

        # Validate response structure
        assert "cards" in info and len(info["cards"]) == 2

        # Ensure pair relationship analysis exists
        assert "pair_dependencies" in info

        # Request an additional card based on:
        # - target position ("3")
        # - full generated sequence
        # - already selected cards
        extra = await mcp.get_additional_card("3", seq, cards)

        # Validate additional card response
        assert "card" in extra

        # Print small success payload for manual verification
        print(
            json.dumps(
                {
                    "ok": True,
                    "sample_card": info["cards"][0]["name"],
                },
                indent=2,
            )
        )


# Entry point for standalone execution
if __name__ == "__main__":
    asyncio.run(main())