"""Fábrica de adaptadores del servicio de Cotización (sin framework de DI)."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.fakes import FakeCache, FakeCotizacionRepository, FakePerfilRiesgo
from app.adapters.perfil_cache import PerfilRiesgoCacheado
from app.adapters.perfilador_client import PerfiladorClient
from app.config import Settings
from app.ports import CachePort, CotizacionRepositoryPort, PerfilRiesgoPort
from app.resilience import ResilientHttpClient, build_breaker


@dataclass
class Dependencias:
    perfilador: PerfilRiesgoPort
    repositorio: CotizacionRepositoryPort
    cache: CachePort

    async def aclose(self) -> None:
        for adaptador in (self.perfilador, self.repositorio, self.cache):
            cerrar = getattr(adaptador, "aclose", None)
            if cerrar is not None:
                await cerrar()


def build_cache(settings: Settings) -> CachePort:
    if settings.cache_backend == "redis":  # pragma: no cover
        from app.adapters.redis_cache import RedisCache

        return RedisCache(settings.redis_url, settings.perfil_cache_ttl_seconds)
    return FakeCache()


def build_dependencias(settings: Settings) -> Dependencias:
    repositorio = FakeCotizacionRepository()  # persistencia real = Fase C

    if settings.adapters == "fake":
        return Dependencias(
            perfilador=FakePerfilRiesgo(), repositorio=repositorio, cache=FakeCache()
        )

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
        cache = build_cache(settings)
        return Dependencias(
            perfilador=PerfilRiesgoCacheado(PerfiladorClient(http), cache),
            repositorio=repositorio,
            cache=cache,
        )

    raise ValueError(f"adapters no soportado: {settings.adapters}")
