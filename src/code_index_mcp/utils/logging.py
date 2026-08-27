from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",     # cyan
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def configure_logging(
    level: str | None = None,
    *,
    dev_mode: bool = False,
    log_dir: Path | None = None,
) -> None:
    if level is None:
        level = "DEBUG" if dev_mode else "INFO"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates on re-configuration
    root.handlers.clear()

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    color_handler = logging.StreamHandler(sys.stderr)
    color_handler.setFormatter(ColorFormatter(fmt, datefmt=datefmt))
    root.addHandler(color_handler)

    if log_dir is None:
        log_dir = Path.home() / ".code-index-mcp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    dated = log_dir / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(dated, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(file_handler)
