"""OpenAI-compatible chat completions client (vLLM compatible)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

from client.config import LLMConfig


class LLMError(Exception):
    """Raised when the LLM API request fails."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class LLMClient:
    """Call chat completions on an OpenAI-compatible HTTP API."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        base = config.base_url.rstrip("/")
        self._url = f"{base}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self._headers = headers

    @property
    def base_url(self) -> str:
        """Configured API base URL."""
        return self._config.base_url

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
    ) -> str:
        """Send a chat completion request and return assistant text.

        Args:
            messages: OpenAI-style message list.
            temperature: Optional override for sampling temperature.

        Returns:
            Assistant message content string.

        Raises:
            LLMError: On transport, HTTP, or malformed response errors.
        """
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature
            if temperature is not None
            else self._config.temperature,
        }

        logger.debug(
            "LLM request: model=%s messages=%d url=%s",
            self._config.model,
            len(messages),
            self._url,
        )

        logger.debug(
            f"LLM messages: {json.dumps(messages)}"
        )

        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                response = client.post(
                    self._url, headers=self._headers, json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            logger.warning("LLM connection failed: %s", exc)
            host = urlparse(self._config.base_url).netloc or self._config.base_url
            raise LLMError(
                f"Cannot connect to LLM server ({host}). "
                "Check llm.base_url in config/client.yaml or set LLM_BASE_URL."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.warning("LLM request timed out")
            raise LLMError(
                f"LLM request timed out after {self._config.timeout_seconds}s."
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "LLM HTTP error: status=%s", exc.response.status_code
            )
            detail = exc.response.text.strip()
            if len(detail) > 200:
                detail = detail[:200] + "..."
            raise LLMError(
                f"LLM API returned HTTP {exc.response.status_code}"
                + (f": {detail}" if detail else ".")
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("LLM request failed: %s", exc)
            raise LLMError(f"LLM request failed: {exc}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise LLMError("LLM response contained no choices")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            text = content.strip()
            logger.debug("LLM response received (%d chars)", len(text))
            logger.debug(f"LLM response: {content}")
            return text

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        parts.append(str(text))
            if parts:
                text = "\n".join(parts).strip()
                logger.debug("LLM response received (%d chars)", len(text))
                return text

        logger.warning("LLM response contained empty assistant content")
        raise LLMError("LLM response contained empty assistant content")
