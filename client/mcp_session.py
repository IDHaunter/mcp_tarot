"""Async MCP client session for tarot tools."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from client.config import MCPConfig

logger = logging.getLogger(__name__)


class TarotMCPClient:
    """Thin wrapper around MCP tool calls for the tarot server."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def generate_sequence(self) -> dict[str, dict[str, str | bool]]:
        """Call Tool #1: generate_tarot_sequence.

        Returns:
            dictionary with shuffled cards

            {
                "1": {"id": "07", "reversed": False},
                "2": {"id": "c03", "reversed": True},
                ...
                "78": {"id": "w11", "reversed": True}
            }
        """
        logger.debug("MCP tool call: generate_tarot_sequence")
        result = await self._session.call_tool("generate_tarot_sequence", {})
        data = _tool_result_to_dict(result)
        logger.debug("MCP tool done: generate_tarot_sequence (%d cards)", len(data))
        return data

    async def get_card_information(
        self, cards: list[dict[str, str | bool]]
    ) -> dict[str, Any]:
        """Call Tool #2: get_card_information."""
        logger.debug(
            "MCP tool call: get_card_information cards=%s",
            [c.get("id") for c in cards],
        )
        result = await self._session.call_tool(
            "get_card_information",
            {"cards": cards},
        )
        data = _tool_result_to_dict(result)
        logger.debug(
            "MCP tool done: get_card_information (%d payloads)",
            len(data.get("cards", [])),
        )
        return data

    async def get_additional_card(
        self,
        position_id: str,
        sequence: dict[str, dict[str, str | bool]],
        already_drawn: list[dict[str, str | bool]],
    ) -> dict[str, Any]:
        """Call Tool #3: get_additional_card."""
        logger.debug(
            "MCP tool call: get_additional_card position=%s drawn=%s",
            position_id,
            [c.get("id") for c in already_drawn],
        )
        result = await self._session.call_tool(
            "get_additional_card",
            {
                "position_id": position_id,
                "sequence": sequence,
                "already_drawn": already_drawn,
            },
        )
        data = _tool_result_to_dict(result)
        logger.debug("MCP tool done: get_additional_card")
        return data


def _tool_result_to_dict(result: Any) -> dict[str, Any]:
    """Parse MCP CallToolResult content into a dict."""
    if result.isError:
        text = _extract_text(result)
        raise RuntimeError(text or "MCP tool returned an error")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return _normalize_tool_payload(structured)

    text = _extract_text(result)
    if not text:
        return {}

    parsed: Any = json.loads(text)
    if isinstance(parsed, dict):
        return _normalize_tool_payload(parsed)
    return {"data": parsed}


def _normalize_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap FastMCP JSON-string tool results when needed."""
    if "error" in payload and len(payload) == 1:
        raise RuntimeError(str(payload["error"]))

    inner = payload.get("result")
    if isinstance(inner, str):
        try:
            nested: Any = json.loads(inner)
            if isinstance(nested, dict):
                if "error" in nested:
                    raise RuntimeError(str(nested["error"]))
                return nested
        except json.JSONDecodeError:
            pass

    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    return payload


def _extract_text(result: Any) -> str:
    """Concatenate text blocks from a tool result."""
    chunks: list[str] = []
    for block in result.content:
        if block.type == "text":
            chunks.append(block.text)
    return "\n".join(chunks).strip()


@asynccontextmanager
async def open_tarot_mcp(config: MCPConfig) -> AsyncIterator[TarotMCPClient]:
    """Connect to the tarot MCP server over stdio.

    Args:
        config: Subprocess launch settings.

    Yields:
        Connected ``TarotMCPClient``.
    """
    cwd = config.cwd
    params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env or None,
        cwd=cwd,
    )
    logger.debug(
        "Starting MCP subprocess: command=%s args=%s cwd=%s",
        config.command,
        config.args,
        cwd,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            logger.debug("MCP session initialized")
            yield TarotMCPClient(session)
