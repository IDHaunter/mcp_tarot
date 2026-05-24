"""Entry point for the tarot MCP server (stdio transport)."""

from server.app import mcp


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
