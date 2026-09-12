"""Fábrica de adaptadores del servicio de Cotización (sin framework de DI)."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.fakes import FakeCotizacionRepository, FakePerfilRiesgo
from app.adapters.perfilador_client import PerfiladorClient
from app.config import Settings
from app.ports import CotizacionRepositoryPort, PerfilRiesgoPort
from app.resilience import ResilientHttpClient, build_breaker


@dataclass
class Dependencias:
    perfilador: PerfilRiesgoPort
    repositorio: CotizacionRepositoryPort

    async def aclose(self) -> None:
        for adaptador in (self.perfilador, self.repositorio):
            cerrar = getattr(adaptador, "aclose", None)
            if cerrar is not None:
                await cerrar()


def build_dependencias(settings: Settings) -> Dependencias:
    repositorio = FakeCotizacionRepository()  # persistencia real = Fase C

    if settings.adapters == "fake":
        return Dependencias(perfilador=FakePerfilRiesgo(), repositorio=repositorio)

    if settings.adapters == "http":
        http = ResilientHttpClient(
            settings.perfilamiento_base_url,
            breaker=build_breaker(
                "perfilamiento",
                fail_max=settings.circuit_fail_max,
                reset_timeout=settings.circuit_reset_timeout_seconds,
            ),
            timeout=settings.http_timeout_seconds,
            retries=settings.http_retries,
        )
        return Dependencias(perfilador=PerfiladorClient(http), repositorio=repositorio)

    raise ValueError(f"adapters no soportado: {settings.adapters}")
