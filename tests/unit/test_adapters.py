from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.factory import build_dependencias
from app.adapters.fakes import FakeCotizacionRepository, FakeProveedorTarifa
from app.config import Settings
from app.domain import (
    Canal,
    Dispositivo,
    EstadoCotizacion,
    Ramo,
    RecursoNoEncontrado,
    Solicitante,
    SolicitudCotizacion,
    TipoCanal,
    TipoDispositivo,
)
from app.services import CotizacionService


def _solicitud() -> SolicitudCotizacion:
    return SolicitudCotizacion(
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        canal=Canal(TipoCanal.SOCIO, "banco-x"),
        dispositivo=Dispositivo(TipoDispositivo.CELULAR, Decimal("3000000"), 8),
        solicitante=Solicitante(28, "CO"),
    )


def test_factory_modo_fake_arma_dependencias():
    deps = build_dependencias(Settings(adapters="fake"))
    assert isinstance(deps.proveedor, FakeProveedorTarifa)
    assert isinstance(deps.repositorio, FakeCotizacionRepository)


def test_factory_modo_no_soportado_lanza():
    with pytest.raises(ValueError):
        build_dependencias(Settings(adapters="sql"))


async def test_service_de_punta_a_punta_con_fakes():
    deps = build_dependencias(Settings(adapters="fake"))
    service = CotizacionService(deps.proveedor, deps.repositorio)

    cot = await service.crear_cotizacion(_solicitud())

    assert cot.estado == EstadoCotizacion.VIGENTE
    assert cot.prima.total > 0
    guardada = await deps.repositorio.obtener(cot.id)
    assert guardada == cot


async def test_proveedor_fake_rechaza_ramo_desconocido():
    with pytest.raises(RecursoNoEncontrado):
        await FakeProveedorTarifa().obtener_tarifa("RAMO_INEXISTENTE")


async def test_repo_fake_obtener_inexistente_lanza():
    with pytest.raises(RecursoNoEncontrado):
        await FakeCotizacionRepository().obtener("no-existe")


async def test_dependencias_aclose_no_falla_con_fakes():
    await build_dependencias(Settings(adapters="fake")).aclose()
