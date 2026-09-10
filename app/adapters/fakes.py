"""Adaptadores en memoria. Corren el servicio standalone y sirven de dobles en pruebas."""

from __future__ import annotations

from decimal import Decimal

from app.domain import Cobertura, Cotizacion, Ramo, RecursoNoEncontrado, Tarifa

# Tarifa de referencia para protección de dispositivos (valores de ejemplo, no actuariales).
_TARIFA_DISPOSITIVO = Tarifa(
    ramo=Ramo.PROTECCION_DISPOSITIVO,
    tasa_base_anual=Decimal("0.045"),
    recargo_gastos=Decimal("0.15"),
    tasa_impuesto=Decimal("0.19"),
    coberturas=(
        Cobertura("ROBO", "Robo y hurto", Decimal("5000000"), Decimal("200000")),
        Cobertura("DANO_ACC", "Daño accidental", Decimal("5000000"), Decimal("300000")),
    ),
)


class FakeProveedorTarifa:
    """Devuelve una tarifa fija en memoria."""

    def __init__(self, tarifa: Tarifa | None = None) -> None:
        self._tarifa = tarifa or _TARIFA_DISPOSITIVO

    async def obtener_tarifa(self, ramo: Ramo) -> Tarifa:
        if ramo != self._tarifa.ramo:
            raise RecursoNoEncontrado(f"no hay tarifa para el ramo {ramo}")
        return self._tarifa


class FakeCotizacionRepository:
    """Guarda cotizaciones en un dict en memoria."""

    def __init__(self) -> None:
        self._por_id: dict[str, Cotizacion] = {}

    async def guardar(self, cotizacion: Cotizacion) -> None:
        self._por_id[cotizacion.id] = cotizacion

    async def obtener(self, cotizacion_id: str) -> Cotizacion:
        cotizacion = self._por_id.get(cotizacion_id)
        if cotizacion is None:
            raise RecursoNoEncontrado("cotización no encontrada")
        return cotizacion
