from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.adapters.factory import build_dependencias
from app.adapters.fakes import FakeCache, FakeCotizacionRepository, FakePerfilRiesgo
from app.adapters.perfil_cache import PerfilRiesgoCacheado
from app.config import Settings
from app.domain import (
    ActividadFisica,
    Cotizacion,
    CuestionarioHabitos,
    DatosCredito,
    DependenciaNoDisponible,
    EstadoCotizacion,
    Moneda,
    NivelRiesgo,
    Oferta,
    RecursoNoEncontrado,
    SolicitudCotizacion,
    Vigencia,
)
from app.services import CotizacionService


def _solicitud(**habitos) -> SolicitudCotizacion:
    base = {
        "consume_tabaco": False,
        "actividad_fisica": ActividadFisica.OCASIONAL,
        "condiciones_preexistentes": False,
        "dependientes_economicos": 1,
    }
    base.update(habitos)
    return SolicitudCotizacion(
        cliente_id="cli-1",
        datos_credito=DatosCredito(
            valor_credito=Decimal("150000000"),
            plazo_meses=240,
            edad=38,
            entidad_acreedora="Banco X",
            saldo_insoluto=Decimal("140000000"),
        ),
        cuestionario_habitos=CuestionarioHabitos(**base),
    )


async def test_perfilador_fake_devuelve_perfil_fijo():
    perfil = await FakePerfilRiesgo().obtener_perfil("cli-1")
    assert perfil.nivel_riesgo == NivelRiesgo.BAJO
    assert perfil.factor_ajuste < Decimal("1.00")


async def test_perfilador_fake_caido_lanza():
    with pytest.raises(DependenciaNoDisponible):
        await FakePerfilRiesgo(disponible=False).obtener_perfil("cli-1")


async def test_perfilador_fake_sin_perfil_calculado_devuelve_none():
    assert await FakePerfilRiesgo(existe=False).obtener_perfil("cli-1") is None


def _cotizacion(cliente_id: str = "cli-1", cot_id: str = "cot-1") -> Cotizacion:
    ahora = datetime.now(UTC)
    return Cotizacion(
        id=cot_id,
        cliente_id=cliente_id,
        estado=EstadoCotizacion.VIGENTE,
        oferta=Oferta(
            prima_mensual=Decimal("60000"),
            prima_base_mensual=Decimal("60000"),
            suma_asegurada=Decimal("140000000"),
            cobertura_meses=240,
            moneda=Moneda.COP,
            personalizado=False,
        ),
        perfil_riesgo=None,
        vigencia=Vigencia(ahora, ahora + timedelta(days=30)),
        creada_en=ahora,
    )


async def test_repo_fake_guarda_y_recupera():
    repo = FakeCotizacionRepository()
    await repo.guardar(_cotizacion())
    assert (await repo.obtener("cot-1", "cli-1")).id == "cot-1"


async def test_repo_fake_rechaza_inexistente_y_cliente_ajeno():
    repo = FakeCotizacionRepository()
    await repo.guardar(_cotizacion())
    with pytest.raises(RecursoNoEncontrado):
        await repo.obtener("no-existe", "cli-1")
    with pytest.raises(RecursoNoEncontrado):
        await repo.obtener("cot-1", "otro")


def test_factory_modo_fake():
    deps = build_dependencias(Settings(adapters="fake"))
    assert isinstance(deps.perfilador, FakePerfilRiesgo)
    assert isinstance(deps.repositorio, FakeCotizacionRepository)


def test_factory_modo_no_soportado_lanza():
    with pytest.raises(ValueError):
        build_dependencias(Settings(adapters="sql"))


async def test_service_de_punta_a_punta_con_fakes():
    deps = build_dependencias(Settings(adapters="fake"))
    cot = await CotizacionService(deps.perfilador, deps.repositorio).crear_cotizacion(_solicitud())
    assert cot.oferta.prima_mensual > 0
    assert (await deps.repositorio.obtener(cot.id, "cli-1")) == cot


async def test_dependencias_aclose_con_fakes():
    await build_dependencias(Settings(adapters="fake")).aclose()


def test_factory_modo_http_arma_cliente_resiliente_con_cache():
    deps = build_dependencias(Settings(adapters="http"))
    assert isinstance(deps.perfilador, PerfilRiesgoCacheado)
    assert isinstance(deps.cache, FakeCache)  # cache_backend="memory" por defecto


async def test_dependencias_aclose_cierra_el_cliente_http():
    await build_dependencias(Settings(adapters="http")).aclose()
