"""Run the backend:  python -m backend   (or: uvicorn backend.server:app)"""
from __future__ import annotations

import uvicorn

from .config import get_config


def main() -> None:
    cfg = get_config()
    uvicorn.run("backend.server:app", host=cfg.host, port=cfg.port, reload=False)


if __name__ == "__main__":
    main()
