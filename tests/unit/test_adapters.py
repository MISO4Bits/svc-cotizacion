from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.factory import build_dependencias
from app.adapters.fakes import (
    FakeCache,
    FakeCotizacionRepository,
    FakePerfilRiesgo,
    FakeTarifa,
    FakeTarifaCache,
)
from app.adapters.perfil_cache import PerfilRiesgoCacheado
from app.adapters.sqlite import SqliteCotizacionRepository
from app.adapters.tarifa_cache import TarifaCacheada
from app.config import Settings
from app.domain import DependenciaNoDisponible, NivelRiesgo, RecursoNoEncontrado
from app.services import CotizacionService
from tests.factories import cotizacion, solicitud


async def test_perfilador_fake_devuelve_perfil_fijo():
    perfil = await FakePerfilRiesgo().obtener_perfil("cli-1")
    assert perfil.nivel_riesgo == NivelRiesgo.BAJO
    assert perfil.factor_ajuste < Decimal("1.00")


async def test_perfilador_fake_caido_lanza():
    with pytest.raises(DependenciaNoDisponible):
        await FakePerfilRiesgo(disponible=False).obtener_perfil("cli-1")


async def test_perfilador_fake_sin_perfil_calculado_devuelve_none():
    assert await FakePerfilRiesgo(existe=False).obtener_perfil("cli-1") is None


async def test_tarifa_fake_caida_lanza():
    with pytest.raises(DependenciaNoDisponible):
        await FakeTarifa(disponible=False).obtener()


async def test_repo_fake_guarda_y_recupera_la_activa():
    repo = FakeCotizacionRepository()
    await repo.reemplazar(cotizacion())
    assert (await repo.obtener_activa("cli-1")).cliente_id == "cli-1"


async def test_repo_fake_reemplaza_la_anterior_y_rechaza_cliente_sin_cotizacion():
    repo = FakeCotizacionRepository()
    await repo.reemplazar(cotizacion(personalizado=False))
    await repo.reemplazar(cotizacion(personalizado=True))

    assert (await repo.obtener_activa("cli-1")).oferta.personalizado is True
    with pytest.raises(RecursoNoEncontrado):
        await repo.obtener_activa("otro")


def test_factory_modo_fake():
    deps = build_dependencias(Settings(adapters="fake"))
    assert isinstance(deps.perfilador, FakePerfilRiesgo)
    assert isinstance(deps.tarifa, FakeTarifa)
    assert isinstance(deps.repositorio, FakeCotizacionRepository)
    assert deps.database is None


def test_factory_modo_no_soportado_lanza():
    with pytest.raises(ValueError):
        build_dependencias(Settings(adapters="sql"))


def test_factory_persistencia_no_soportada_lanza():
    with pytest.raises(ValueError):
        build_dependencias(Settings(adapters="fake", repository_backend="mongo"))


async def test_factory_persistencia_sqlite_crea_el_esquema(tmp_path):
    deps = build_dependencias(
        Settings(adapters="fake", repository_backend="sqlite", database_path=str(tmp_path / "c.db"))
    )
    assert isinstance(deps.repositorio, SqliteCotizacionRepository)

    await deps.init()

    assert (tmp_path / "c.db").exists()


async def test_service_de_punta_a_punta_con_fakes():
    deps = build_dependencias(Settings(adapters="fake"))
    servicio = CotizacionService(deps.perfilador, deps.tarifa, deps.repositorio, deps.eventos)

    cot = await servicio.crear_cotizacion(solicitud())

    assert cot.oferta.prima_mensual > 0
    assert (await deps.repositorio.obtener_activa("cli-1")) == cot


async def test_dependencias_aclose_con_fakes():
    await build_dependencias(Settings(adapters="fake")).aclose()


def test_factory_modo_http_arma_clientes_resilientes_con_cache():
    deps = build_dependencias(Settings(adapters="http"))
    assert isinstance(deps.perfilador, PerfilRiesgoCacheado)
    assert isinstance(deps.tarifa, TarifaCacheada)
    assert isinstance(deps.cache, FakeCache)  # cache_backend="memory" por defecto


async def test_dependencias_aclose_cierra_los_clientes_http():
    await build_dependencias(Settings(adapters="http")).aclose()


async def test_tarifa_cache_fake_guarda_y_devuelve():
    cache = FakeTarifaCache()
    assert await cache.obtener() is None
    tarifa = await FakeTarifa().obtener()
    await cache.guardar(tarifa)
    assert await cache.obtener() == tarifa
