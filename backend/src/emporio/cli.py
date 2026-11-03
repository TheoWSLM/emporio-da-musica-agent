"""Command-line entry point: `emporio <command>`."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from emporio.config import get_settings
from emporio.infrastructure.db import create_engine, create_session_factory
from emporio.ingestion.loader import load_raw_dataset
from emporio.ingestion.pipeline import ingest_structured
from emporio.ingestion.quality import analyze, render_markdown


async def _ingest(force: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        await ingest_structured(create_session_factory(engine), settings.data_dir, force=force)
    finally:
        await engine.dispose()


def _data_report(output: Path) -> None:
    dataset = load_raw_dataset(get_settings().data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(dataset, analyze(dataset)), encoding="utf-8")
    print(f"wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="emporio")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="load data/raw into Postgres (idempotent)")
    ingest.add_argument("--force", action="store_true", help="reload even if inputs are unchanged")
    report = commands.add_parser("data-report", help="write the data-quality report")
    report.add_argument("--output", type=Path, default=Path("reports/data-quality.md"))

    args = parser.parse_args()
    logging.basicConfig(
        level=get_settings().log_level, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.command == "ingest":
        asyncio.run(_ingest(args.force))
    elif args.command == "data-report":
        _data_report(args.output)


if __name__ == "__main__":
    main()
