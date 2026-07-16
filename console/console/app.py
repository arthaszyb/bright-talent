"""Entry point: `python -m console.app --repo <de-demo root> --port <p>`."""
from __future__ import annotations

import argparse

import uvicorn

from .api import build_app
from .config import Config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="console.app", description="DE fleet governance console")
    p.add_argument("--repo", required=True, help="Path to the de-demo repo root")
    p.add_argument("--port", type=int, default=8900, help="HTTP port (default 8900)")
    p.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    p.add_argument("--db-path", default=None, help="Override SQLite DB path (default: console/data/console.db)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = Config.from_args(repo=args.repo, port=args.port, db_path=args.db_path)
    app = build_app(config)
    uvicorn.run(app, host=args.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
