"""Configure file logging for the tarot client."""

from __future__ import annotations

import logging
from pathlib import Path

from client.config import LoggingConfig

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CLIENT_LOGGER_NAME = "client"


def parse_log_level(level: str) -> int:
    """Convert standard level name to logging module constant.

    Args:
        level: Name such as DEBUG, INFO, WARNING, ERROR, CRITICAL.

    Returns:
        Numeric level accepted by the logging module.

    Raises:
        ValueError: If the level name is not recognized.
    """
    normalized = level.strip().upper()
    mapping = logging.getLevelNamesMapping()
    if normalized not in mapping:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(
            f"Unknown log level {level!r}. Use one of: {allowed}"
        )
    return mapping[normalized]


def resolve_log_path(file_path: str, base_dir: Path) -> Path:
    """Resolve log file path relative to project base when not absolute."""
    path = Path(file_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def setup_logging(config: LoggingConfig, *, base_dir: Path) -> logging.Logger:
    """Attach a single append-only file handler to the client logger tree.

    Args:
        config: Logging section from client.yaml.
        base_dir: Project root for relative log file paths.

    Returns:
        Configured root logger for the ``client`` package.
    """
    numeric_level = parse_log_level(config.level)
    log_path = resolve_log_path(config.file, base_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    client_logger = logging.getLogger(CLIENT_LOGGER_NAME)
    client_logger.setLevel(numeric_level)
    client_logger.propagate = False

    for handler in list(client_logger.handlers):
        client_logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(
        log_path,
        mode="a",
        encoding="utf-8",
    )
    handler.setLevel(numeric_level)
    handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    )
    client_logger.addHandler(handler)

    client_logger.debug(
        "Logging initialized: level=%s file=%s",
        config.level.upper(),
        log_path,
    )
    return client_logger
