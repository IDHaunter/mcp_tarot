"""OpenAI-compatible chat completions client (vLLM compatible)."""

from __future__ import annotations

from typing import Any

import httpx

from client.config import LLMConfig


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
            httpx.HTTPError: On transport or HTTP errors.
            RuntimeError: If the response has no assistant content.
        """
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature
            if temperature is not None
            else self._config.temperature,
        }

        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            response = client.post(self._url, headers=self._headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("LLM response contained no choices")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        parts.append(str(text))
            if parts:
                return "\n".join(parts).strip()

        raise RuntimeError("LLM response contained empty assistant content")
