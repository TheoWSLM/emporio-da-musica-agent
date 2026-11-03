"""FastAPI application factory."""

from fastapi import FastAPI

from emporio.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Empório da Música — Customer Service Agent",
        version=settings.release_id,
    )

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "release": settings.release_id}

    return app


app = create_app()
