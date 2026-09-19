"""Cubre el ciclo de vida (startup/shutdown) de la app — antes nunca se
ejercía porque ningún test dispara los eventos de lifespan de ASGI (el
``client`` de conftest.py usa ``ASGITransport`` directo, sin lifespan).
Mismo hueco que se encontró en svc-perfilamiento (Sonar PR #2) — se cubre
acá antes de que toque este PR."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import Settings


def test_lifespan_arranca_y_detiene_limpiamente():
    app = create_app(Settings(adapters="fake"))
    with TestClient(app):
        pass
