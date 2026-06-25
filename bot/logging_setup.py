"""Logging configuration with a rich console handler + rotating file handler."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from rich.logging import RichHandler

_CONFIGURED = False


def setup_logging(level: str = "INFO", file: str | None = None, json: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level.upper())
    # Clear any default handlers (uvicorn / libraries may add their own).
    for h in list(root.handlers):
        root.removeHandler(h)

    console = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
    console.setFormatter(logging.Formatter("%(name)s: %(message)s", datefmt="[%X]"))
    root.addHandler(console)

    if file:
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        fmt = (
            '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
            if json
            else "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
        )
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)

    # Quiet noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "web3", "websockets", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
