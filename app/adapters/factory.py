"""Fábrica de adaptadores del servicio de Cotización (sin framework de DI)."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.fakes import (
    FakeCache,
    FakeCotizacionRepository,
    FakePerfilRiesgo,
    FakeTarifa,
    FakeTarifaCache,
)
from app.adapters.perfil_cache import PerfilRiesgoCacheado
from app.adapters.perfilador_client import PerfiladorClient
from app.adapters.sqlite import SqliteCotizacionRepository, SqliteDatabase
from app.adapters.tarifa_cache import TarifaCacheada
from app.adapters.tarifa_client import TarifaClient
from app.config import Settings
from app.ports import (
    CachePort,
    CotizacionRepositoryPort,
    PerfilRiesgoPort,
    TarifaCachePort,
    TarifaPort,
)
from app.resilience import ResilientHttpClient, build_breaker


@dataclass
class Dependencias:
    perfilador: PerfilRiesgoPort
    tarifa: TarifaPort
    repositorio: CotizacionRepositoryPort
    cache: CachePort
    database: SqliteDatabase | None = None

    async def init(self) -> None:
        """Crea el esquema si la persistencia está respaldada por SQLite."""
        if self.database is not None:
            await self.database.init()

    async def aclose(self) -> None:
        for adaptador in (self.perfilador, self.tarifa, self.repositorio, self.cache):
            cerrar = getattr(adaptador, "aclose", None)
            if cerrar is not None:
                await cerrar()


def build_cache(settings: Settings) -> CachePort:
    if settings.cache_backend == "redis":  # pragma: no cover
        from app.adapters.redis_cache import RedisCache

        return RedisCache(settings.redis_url, settings.perfil_cache_ttl_seconds)
    return FakeCache()


def build_tarifa_cache(settings: Settings) -> TarifaCachePort:
    if settings.cache_backend == "redis":  # pragma: no cover
        from app.adapters.redis_cache import RedisTarifaCache

        return RedisTarifaCache(settings.redis_url, settings.tarifa_cache_ttl_seconds)
    return FakeTarifaCache()


def build_persistencia(
    settings: Settings,
) -> tuple[CotizacionRepositoryPort, SqliteDatabase | None]:
    if settings.repository_backend == "memory":
        return FakeCotizacionRepository(), None
    if settings.repository_backend == "sqlite":
        db = SqliteDatabase(settings.database_path)
        return SqliteCotizacionRepository(db), db
    raise ValueError(f"repository_backend no soportado: {settings.repository_backend}")


def build_dependencias(settings: Settings) -> Dependencias:
    repositorio, database = build_persistencia(settings)

    if settings.adapters == "fake":
        return Dependencias(
            perfilador=FakePerfilRiesgo(),
            tarifa=FakeTarifa(),
            repositorio=repositorio,
            cache=FakeCache(),
            database=database,
        )

    if settings.adapters == "http":
        http_perfilamiento = ResilientHttpClient(
            settings.perfilamiento_base_url,
            breaker=build_breaker(
                "perfilamiento",
                fail_max=settings.circuit_fail_max,
                reset_timeout=settings.circuit_reset_timeout_seconds,
            ),
            timeout=settings.http_timeout_seconds,
            retries=settings.http_retries,
        )
        http_productos = ResilientHttpClient(
            settings.productos_base_url,
            breaker=build_breaker(
                "productos",
                fail_max=settings.circuit_fail_max,
                reset_timeout=settings.circuit_reset_timeout_seconds,
            ),
            timeout=settings.productos_timeout_seconds,
            retries=settings.productos_retries,
        )
        cache = build_cache(settings)
        return Dependencias(
            perfilador=PerfilRiesgoCacheado(PerfiladorClient(http_perfilamiento), cache),
            tarifa=TarifaCacheada(TarifaClient(http_productos), build_tarifa_cache(settings)),
            repositorio=repositorio,
            cache=cache,
            database=database,
        )

    raise ValueError(f"adapters no soportado: {settings.adapters}")
