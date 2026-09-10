"""Puertos de salida del servicio de Cotización.

Contratos que el servicio necesita del mundo exterior. Las implementaciones
concretas (en memoria, HTTP, base de datos) viven en ``app/adapters/`` y se
eligen en ``adapters/factory.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import Cotizacion, Ramo, Tarifa


@runtime_checkable
class ProveedorTarifaPort(Protocol):
    async def obtener_tarifa(self, ramo: Ramo) -> Tarifa:
        """Devuelve los factores de tarifa vigentes para el ramo.

        En la Fase D esta es la dependencia que el experimento de resiliencia
        degrada (timeout, 5xx, desconexión). Lanza ``DependenciaNoDisponible``
        si la fuente no responde a tiempo.
        """
        ...


@runtime_checkable
class CotizacionRepositoryPort(Protocol):
    async def guardar(self, cotizacion: Cotizacion) -> None:
        """Persiste una cotización nueva."""
        ...

    async def obtener(self, cotizacion_id: str) -> Cotizacion:
        """Recupera una cotización por id. Lanza ``RecursoNoEncontrado`` si no existe."""
        ...
