#!/usr/bin/env python3
"""Post-deploy smoke test (standard library only).

    python3 scripts/smoke.py http://127.0.0.1:18082 [--neighbour URL ...] [--check-rate-limit N]

Checks /api/health, creates a conversation, asks a real question and requires a non-empty answer over
SSE. Optionally checks that neighbour apps still answer 200 and that the rate limit returns 429 (it sends
cheap off-topic messages, which never reach the agent).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _request(url: str, data: dict | None = None, timeout: float = 90) -> tuple[int, str]:  # type: ignore[type-arg]
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "emporio-smoke/1.0")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def events(sse_body: str) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line[5:].strip()) for line in sse_body.splitlines() if line.startswith("data:")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--neighbour", action="append", default=[], help="URL that must still answer 200")
    parser.add_argument("--check-rate-limit", type=int, default=0, metavar="LIMIT")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    failures: list[str] = []

    status, body = _request(f"{base}/api/health", timeout=10)
    print(f"health: {status} {body}")
    if status != 200:
        failures.append("health")

    status, body = _request(f"{base}/api/conversations", data={})
    conversation = json.loads(body)["conversation_id"] if status == 201 else None
    if conversation is None:
        failures.append(f"create conversation ({status})")
    else:
        status, body = _request(f"{base}/api/conversations/{conversation}/messages", {"content": "Qual o horário da loja?"})
        message = next((e for e in events(body) if e.get("type") == "message"), None)
        answer = message["reply"]["message"] if message else ""
        print(f"answer ({status}): {answer[:160]!r}")
        if status != 200 or not answer:
            failures.append("chat answer")

    for url in args.neighbour:
        status, _ = _request(url, timeout=15)
        print(f"neighbour {url}: {status}")
        if status != 200:
            failures.append(f"neighbour {url}")

    if args.check_rate_limit and conversation:
        codes = [
            _request(f"{base}/api/conversations/{conversation}/messages", {"content": "Qual a capital da França?"})[0]
            for _ in range(args.check_rate_limit + 1)
        ]
        print(f"rate limit: {codes}")
        if 429 not in codes:
            failures.append("rate limit never returned 429")

    print("SMOKE OK" if not failures else f"SMOKE FAILED: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
