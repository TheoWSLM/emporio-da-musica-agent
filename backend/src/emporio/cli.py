"""Command-line entry point: `emporio <command>`."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from openai import AsyncOpenAI

from emporio.config import get_settings
from emporio.infrastructure.db import create_engine, create_session_factory
from emporio.ingestion.loader import load_raw_dataset
from emporio.ingestion.pipeline import ingest_embeddings, ingest_structured
from emporio.ingestion.quality import analyze, render_markdown
from emporio.knowledge.infrastructure.embedders import OpenAIEmbedder


async def _ingest(force: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        await ingest_structured(sessions, settings.data_dir, force=force)
        if settings.openai_api_key is None:
            raise SystemExit(
                "OPENAI_API_KEY is not set: cannot build the embeddings (see .env.example)"
            )
        client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        embedder = OpenAIEmbedder(client, settings.embedding_model, settings.embedding_dimensions)
        await ingest_embeddings(
            sessions, settings.data_dir, embedder, settings.embedding_model, force=force
        )
    finally:
        await engine.dispose()


def _data_report(output: Path) -> None:
    dataset = load_raw_dataset(get_settings().data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(dataset, analyze(dataset)), encoding="utf-8")
    print(f"wrote {output}")


async def _conversation(messages: list[str] | None, show_events: bool) -> None:
    """Interactive chat (messages=None) or a scripted one-shot run."""
    from emporio.container import Container

    container = Container.build(get_settings())
    try:
        conversation_id = await container.conversations.create("cli")
        scripted = iter(messages) if messages is not None else None
        print("Lia — Empório da Música (Ctrl+D para sair)\n")
        while True:
            if scripted is not None:
                text = next(scripted, None)
                if text is None:
                    break
                print(f"você> {text}")
            else:
                try:
                    text = (await asyncio.to_thread(input, "você> ")).strip()
                except EOFError:
                    break
                if not text:
                    continue
            async for event in container.assistant.stream(conversation_id, text):
                kind = event["type"]
                if kind == "message":
                    print(f"\nlia> {event['reply']['message']}\n")
                elif show_events and kind == "classification":
                    a = event["assessment"]
                    print(
                        f"  · classifier[{event['provider']} {event['latency_ms']}ms] route={event['route']} intent={a['intent']} scope={a['scope']}"
                    )
                elif show_events and kind == "tool":
                    print(
                        f"  · tool {event['name']}({event['arguments']}) {event['duration_ms']}ms"
                    )
                elif show_events and kind == "status":
                    print(f"  · {event['text']}")
                elif show_events and kind == "done":
                    print(
                        f"  · {event['outcome']} in {event['latency_ms']}ms, {event['model_rounds']} model round(s)"
                    )
    finally:
        await container.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="emporio")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="load data/raw into Postgres (idempotent)")
    ingest.add_argument("--force", action="store_true", help="reload even if inputs are unchanged")
    report = commands.add_parser("data-report", help="write the data-quality report")
    report.add_argument("--output", type=Path, default=Path("reports/data-quality.md"))

    chat = commands.add_parser("chat", help="talk to the agent in the terminal")
    chat.add_argument("--quiet", action="store_true", help="hide classifier/tool events")
    ask = commands.add_parser(
        "ask", help="send scripted messages (one conversation) and print the replies"
    )
    ask.add_argument("messages", nargs="+")

    args = parser.parse_args()
    logging.basicConfig(
        level=get_settings().log_level, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.command == "ingest":
        asyncio.run(_ingest(args.force))
    elif args.command == "data-report":
        _data_report(args.output)
    elif args.command == "chat":
        asyncio.run(_conversation(None, show_events=not args.quiet))
    elif args.command == "ask":
        asyncio.run(_conversation(args.messages, show_events=True))


if __name__ == "__main__":
    main()
