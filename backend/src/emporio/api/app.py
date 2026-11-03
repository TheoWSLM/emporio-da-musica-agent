"""FastAPI application factory (served with `uvicorn --factory emporio.api.app:create_app`)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from emporio.api.rate_limit import DailyBudget, SlidingWindowLimiter
from emporio.api.routes import router
from emporio.api.runtime import Runtime
from emporio.config import Settings, get_settings

log = logging.getLogger(__name__)


def _default_runtime(settings: Settings) -> Runtime:
    from emporio.container import Container

    container = Container.build(settings)
    return Runtime(
        settings=settings,
        assistant=container.assistant,
        conversations=container.conversations,
        ip_limiter=SlidingWindowLimiter(
            settings.rate_limit_per_ip, settings.rate_limit_window_seconds
        ),
        daily_budget=DailyBudget(settings.rate_limit_global_per_day),
        close=container.close,
    )


def create_app(runtime_factory: Callable[[Settings], Runtime] = _default_runtime) -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime_factory(settings)
        yield
        await app.state.runtime.close()

    app = FastAPI(
        title="Empório da Música — Customer Service Agent",
        version=settings.release_id,
        lifespan=lifespan,
        description="Chat API of Lia, the virtual assistant of Empório da Música. "
        "Messages are answered as Server-Sent Events (see the SseEvent schemas).",
    )

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "release": settings.release_id}

    app.include_router(router)
    return app
