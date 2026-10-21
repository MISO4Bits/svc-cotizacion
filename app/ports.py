"""Puertos de salida del servicio de Cotización.

Nombres del diseño de David (Confluence › "Cotización y Rating"). Hoy están los
puertos de perfil, tarifa y cotización; los demás (SenalesExternasPort, EventosPort)
quedan para después.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import Cotizacion, PerfilRiesgo, Tarifa


@runtime_checkable
class PerfilRiesgoPort(Protocol):
    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        """Lee el perfil de riesgo que Perfilamiento ya calculó de forma
        asíncrona (disparado por consentimiento, ver Confluence › página
        Perfilamiento, Sección 8) — una lectura, no un cómputo en caliente.

        ``None`` si Perfilamiento todavía no lo ha calculado (el cliente
        acaba de otorgar consentimiento, o nunca lo otorgó) — no es un
        fallo, el servicio cae a tarifa estándar igual que si la
        dependencia estuviera caída. Es la dependencia que EXP-02 degrada
        (timeout, 5xx, desconexión): lanza ``DependenciaNoDisponible`` si
        Perfilamiento no responde a tiempo; el servicio captura esa
        excepción y cae al mismo fallback (BITS-105 AC-2).
        """
        ...


@runtime_checkable
class CachePort(Protocol):
    """Caché de perfiles de riesgo (Redis en producción) — puramente un
    acelerador de latencia, nunca la fuente de verdad (esa sigue siendo
    Perfilamiento/Spanner). Cualquier fallo del caché debe tratarse como un
    cache miss, nunca como un fallo de la cotización."""

    async def obtener(self, cliente_id: str) -> PerfilRiesgo | None:
        """``None`` tanto si no está en caché como si el caché falló."""
        ...

    async def guardar(self, cliente_id: str, perfil: PerfilRiesgo) -> None:
        """Best-effort — un fallo al guardar no debe propagarse."""
        ...

    async def eliminar(self, cliente_id: str) -> None:
        """Invalida la entrada de un cliente (disparado por
        ConsentimientoRevocado). Silencioso si no existía o si el caché
        falló — el TTL es la red de seguridad en ese caso."""
        ...


@runtime_checkable
class TarifaPort(Protocol):
    async def obtener(self) -> Tarifa:
        """Tabla de tasas por edad vigente.

        Lanza ``DependenciaNoDisponible`` si no se puede obtener — sin tarifa no hay
        precio, así que la cotización falla con 503 (no hay tarifa de reemplazo).
        """
        ...


@runtime_checkable
class TarifaCachePort(Protocol):
    """Caché de la tarifa (Redis en producción): un acelerador, nunca la fuente de verdad
    (esa es Productos). Cualquier fallo del caché se trata como un miss."""

    async def obtener(self) -> Tarifa | None:
        """``None`` tanto si no está en caché como si el caché falló."""
        ...

    async def guardar(self, tarifa: Tarifa) -> None:
        """Best-effort — un fallo al guardar no debe propagarse."""
        ...


@runtime_checkable
class CotizacionRepositoryPort(Protocol):
    async def reemplazar(self, cotizacion: Cotizacion) -> None:
        """Guarda la cotización como la activa del cliente, reemplazando la anterior si la había."""
        ...

    async def obtener_activa(self, cliente_id: str) -> Cotizacion:
        """La cotización activa del cliente. Lanza ``RecursoNoEncontrado`` si no tiene."""
        ...

    async def eliminar_activa(self, cliente_id: str) -> None:
        """Borra la cotización activa del cliente. Lanza ``RecursoNoEncontrado`` si no tiene."""
        ...
