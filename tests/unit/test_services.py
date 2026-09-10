from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain import (
    Canal,
    Cobertura,
    Cotizacion,
    DependenciaNoDisponible,
    Dispositivo,
    EstadoCotizacion,
    Ramo,
    Solicitante,
    SolicitudCotizacion,
    Tarifa,
    TipoCanal,
    TipoDispositivo,
)
from app.services import CotizacionService, calcular_prima


class _ProveedorOk:
    async def obtener_tarifa(self, ramo: Ramo) -> Tarifa:
        return Tarifa(
            ramo=Ramo.PROTECCION_DISPOSITIVO,
            tasa_base_anual=Decimal("0.04"),
            recargo_gastos=Decimal("0.15"),
            tasa_impuesto=Decimal("0.19"),
            coberturas=(Cobertura("ROBO", "Robo y hurto", Decimal("3000000"), Decimal("150000")),),
        )


class _ProveedorCaido:
    async def obtener_tarifa(self, ramo: Ramo) -> Tarifa:
        raise DependenciaNoDisponible("proveedor de tarifa no responde")


class _RepoEnMemoria:
    def __init__(self) -> None:
        self.guardadas: list[Cotizacion] = []

    async def guardar(self, cotizacion: Cotizacion) -> None:
        self.guardadas.append(cotizacion)

    async def obtener(self, cotizacion_id: str) -> Cotizacion:
        for c in self.guardadas:
            if c.id == cotizacion_id:
                return c
        raise KeyError(cotizacion_id)


def _solicitud() -> SolicitudCotizacion:
    return SolicitudCotizacion(
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        canal=Canal(TipoCanal.SOCIO, "banco-x"),
        dispositivo=Dispositivo(TipoDispositivo.CELULAR, Decimal("3000000"), 6),
        solicitante=Solicitante(30, "CO"),
    )


async def test_crear_cotizacion_camino_feliz():
    repo = _RepoEnMemoria()
    service = CotizacionService(_ProveedorOk(), repo)

    cot = await service.crear_cotizacion(_solicitud())

    assert cot.estado == EstadoCotizacion.VIGENTE
    assert cot.ramo == Ramo.PROTECCION_DISPOSITIVO
    assert cot.prima.total == cot.prima.prima_pura + cot.prima.gastos + cot.prima.impuestos
    assert len(cot.coberturas) == 1
    assert cot.vigencia.hasta > cot.vigencia.desde
    assert repo.guardadas == [cot]


async def test_crear_cotizacion_propaga_falla_del_proveedor():
    service = CotizacionService(_ProveedorCaido(), _RepoEnMemoria())
    with pytest.raises(DependenciaNoDisponible):
        await service.crear_cotizacion(_solicitud())


def test_calcular_prima_dispositivo_nuevo():
    disp = Dispositivo(TipoDispositivo.CELULAR, Decimal("2000000"), 6)
    tarifa = Tarifa(
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        tasa_base_anual=Decimal("0.05"),
        recargo_gastos=Decimal("0.10"),
        tasa_impuesto=Decimal("0.19"),
        coberturas=(),
    )
    prima = calcular_prima(disp, tarifa)
    assert prima.prima_pura == Decimal("100000.00")
    assert prima.gastos == Decimal("10000.00")
    assert prima.impuestos == Decimal("20900.00")
    assert prima.total == Decimal("130900.00")


def test_factor_antiguedad_escalonado():
    tarifa = Tarifa(Ramo.PROTECCION_DISPOSITIVO, Decimal("0.04"), Decimal("0"), Decimal("0"), ())

    def pura(meses: int) -> Decimal:
        disp = Dispositivo(TipoDispositivo.PORTATIL, Decimal("1000000"), meses)
        return calcular_prima(disp, tarifa).prima_pura

    assert pura(6) < pura(18) < pura(30)
