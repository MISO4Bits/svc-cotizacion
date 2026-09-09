"""Construcción de la app FastAPI del servicio de Cotización."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.routes import router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(title="svc-cotizacion — Cotización y Rating", version="0.1.0")
    app.state.settings = settings

    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "service": settings.service_name}

    return app
