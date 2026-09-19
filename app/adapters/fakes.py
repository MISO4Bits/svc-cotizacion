"""Adaptadores en memoria. Corren el servicio standalone y sirven de dobles en pruebas."""

from __future__ import annotations

from decimal import Decimal

from app.domain import (
    Cotizacion,
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    NivelRiesgo,
    PerfilRiesgo,
    RecursoNoEncontrado,
)


class FakePerfilRiesgo:
    """Perfilador simulado — perfil fijo, no calcula nada (a diferencia de
    la versión vieja, el contrato real ya no manda datos de la solicitud
    para que Perfilamiento "calcule": ahora es una lectura de un perfil que
    Perfilamiento ya calculó por su cuenta, de forma asíncrona).

    ``disponible=False`` imita a Perfilamiento caído (timeout/5xx).
    ``existe=False`` imita "perfil no calculado todavía" (sin consentimiento
    otorgado) — caso distinto, mismo fallback.
    """

    def __init__(self, *, disponible: bool = True, existe: bool = True) -> None:
        self._disponible = disponible
        self._existe = existe

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        if not self._disponible:
            raise DependenciaNoDisponible("Perfilamiento no responde")
        if not self._existe:
            return None
        return PerfilRiesgo(
            nivel_riesgo=NivelRiesgo.BAJO,
            factores=(FactorRiesgo("Perfil simulado", EfectoFactor.POSITIVO, Decimal("0.2")),),
            factor_ajuste=Decimal("0.90"),
        )


class FakeCache:
    """Caché en memoria — mismo contrato que RedisCache, sin infraestructura real."""

    def __init__(self) -> None:
        self._por_cliente: dict[str, PerfilRiesgo] = {}

    async def obtener(self, cliente_id: str) -> PerfilRiesgo | None:
        return self._por_cliente.get(cliente_id)

    async def guardar(self, cliente_id: str, perfil: PerfilRiesgo) -> None:
        self._por_cliente[cliente_id] = perfil

    async def eliminar(self, cliente_id: str) -> None:
        self._por_cliente.pop(cliente_id, None)


class FakeCotizacionRepository:
    """Guarda cotizaciones en un dict en memoria."""

    def __init__(self) -> None:
        self._por_id: dict[str, Cotizacion] = {}

    async def guardar(self, cotizacion: Cotizacion) -> None:
        self._por_id[cotizacion.id] = cotizacion

    async def obtener(self, cotizacion_id: str, cliente_id: str) -> Cotizacion:
        cotizacion = self._por_id.get(cotizacion_id)
        if cotizacion is None or cotizacion.cliente_id != cliente_id:
            raise RecursoNoEncontrado("cotización no encontrada")
        return cotizacion
