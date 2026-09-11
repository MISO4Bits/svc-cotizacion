"""Puertos de salida del servicio de Cotización.

Nombres del diseño de David (Confluence › "Cotización y Rating"). Para EXP-02 solo
se implementan estos dos; los demás puertos (ReglasRatingPort, CachePort,
SenalesExternasPort, EventosPort) quedan para después.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import Cotizacion, PerfilRiesgo, SolicitudCotizacion


@runtime_checkable
class PerfilRiesgoPort(Protocol):
    async def perfilar(self, solicitud: SolicitudCotizacion) -> PerfilRiesgo:
        """Pide a Perfilamiento el perfil de riesgo y el factor de ajuste del cliente.

        Es la dependencia que EXP-02 degrada (timeout, 5xx, desconexión). Lanza
        ``DependenciaNoDisponible`` si Perfilamiento no responde a tiempo; el
        servicio captura esa excepción y cae a tarifa estándar (BITS-105 AC-2).
        """
        ...


@runtime_checkable
class CotizacionRepositoryPort(Protocol):
    async def guardar(self, cotizacion: Cotizacion) -> None:
        """Persiste una cotización nueva."""
        ...

    async def obtener(self, cotizacion_id: str, cliente_id: str) -> Cotizacion:
        """Recupera una cotización del cliente. Lanza ``RecursoNoEncontrado`` si no existe."""
        ...
