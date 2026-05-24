"""Tests for client.logging_setup."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from client.config import LoggingConfig
from client.logging_setup import (
    CLIENT_LOGGER_NAME,
    parse_log_level,
    resolve_log_path,
    setup_logging,
)


def test_parse_log_level_accepts_standard_names() -> None:
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO
    assert parse_log_level("WARNING") == logging.WARNING


def test_parse_log_level_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown log level"):
        parse_log_level("TRACE")


def test_setup_logging_writes_formatted_line(tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    config = LoggingConfig(level="DEBUG", file=str(log_file))
    setup_logging(config, base_dir=tmp_path)

    test_logger = logging.getLogger(f"{CLIENT_LOGGER_NAME}.test")
    test_logger.info("hello from test")

    content = log_file.read_text(encoding="utf-8")
    assert "INFO" in content
    assert "client.test" in content
    assert "hello from test" in content
    assert len(content.splitlines()) >= 2
