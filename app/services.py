"""Orquestación y rating del servicio de Cotización."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domain import (
    Cotizacion,
    Dispositivo,
    EstadoCotizacion,
    PrimaDesglose,
    SolicitudCotizacion,
    Tarifa,
    Vigencia,
)
from app.ports import CotizacionRepositoryPort, ProveedorTarifaPort

VIGENCIA_COTIZACION = timedelta(days=15)
_CENTAVO = Decimal("0.01")


def _factor_antiguedad(meses: int) -> Decimal:
    if meses <= 12:
        return Decimal("1.0")
    if meses <= 24:
        return Decimal("1.25")
    return Decimal("1.5")


def calcular_prima(dispositivo: Dispositivo, tarifa: Tarifa) -> PrimaDesglose:
    """Rating simple para protección de dispositivos.

    prima_pura = valor_asegurado * tasa_base_anual * factor_por_antiguedad.
    """
    base = dispositivo.valor_asegurado * tarifa.tasa_base_anual
    prima_pura = (base * _factor_antiguedad(dispositivo.antiguedad_meses)).quantize(_CENTAVO)
    gastos = (prima_pura * tarifa.recargo_gastos).quantize(_CENTAVO)
    impuestos = ((prima_pura + gastos) * tarifa.tasa_impuesto).quantize(_CENTAVO)
    total = prima_pura + gastos + impuestos
    return PrimaDesglose(prima_pura, gastos, impuestos, total)


class CotizacionService:
    def __init__(
        self,
        proveedor: ProveedorTarifaPort,
        repositorio: CotizacionRepositoryPort,
    ) -> None:
        self._proveedor = proveedor
        self._repositorio = repositorio

    async def crear_cotizacion(self, solicitud: SolicitudCotizacion) -> Cotizacion:
        tarifa = await self._proveedor.obtener_tarifa(solicitud.ramo)
        prima = calcular_prima(solicitud.dispositivo, tarifa)

        ahora = datetime.now(UTC)
        cotizacion = Cotizacion(
            id=str(uuid4()),
            estado=EstadoCotizacion.VIGENTE,
            ramo=solicitud.ramo,
            prima=prima,
            coberturas=tarifa.coberturas,
            vigencia=Vigencia(ahora, ahora + VIGENCIA_COTIZACION),
            creada_en=ahora,
        )
        await self._repositorio.guardar(cotizacion)
        return cotizacion
