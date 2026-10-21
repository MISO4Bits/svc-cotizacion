"""Adaptadores en memoria. Corren el servicio standalone y sirven de dobles en pruebas."""

from __future__ import annotations

from decimal import Decimal

from app.domain import (
    Cotizacion,
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    FranjaTarifa,
    NivelRiesgo,
    PerfilRiesgo,
    RecursoNoEncontrado,
    Tarifa,
    TarifaHogar,
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


# Tabla de la historia BITS-95 y tarifa de Hogar (misma que la semilla de Productos, versión 2).
TARIFA_SEMILLA = Tarifa(
    version=2,
    franjas=tuple(
        FranjaTarifa(desde, hasta, Decimal(tasa))
        for desde, hasta, tasa in (
            (18, 24, "0.062"),
            (25, 29, "0.095"),
            (30, 34, "0.137"),
            (35, 39, "0.196"),
            (40, 44, "0.281"),
            (45, 49, "0.402"),
            (50, 54, "0.576"),
            (55, 59, "0.826"),
            (60, 65, "1.184"),
        )
    ),
    hogar=TarifaHogar(
        tasa_mensual_por_mil=Decimal("0.099"),
        suma_asegurada_maxima=Decimal("240000000"),
        iva=Decimal("0.19"),
    ),
)


class FakeTarifa:
    """Tarifa simulada — la de la historia. ``disponible=False`` imita a Productos caído."""

    def __init__(self, *, disponible: bool = True, tarifa: Tarifa = TARIFA_SEMILLA) -> None:
        self._disponible = disponible
        self._tarifa = tarifa
        self.llamadas = 0

    async def obtener(self) -> Tarifa:
        self.llamadas += 1
        if not self._disponible:
            raise DependenciaNoDisponible("Productos no responde")
        return self._tarifa


class FakeTarifaCache:
    """Caché de tarifa en memoria — mismo contrato que RedisTarifaCache."""

    def __init__(self) -> None:
        self._tarifa: Tarifa | None = None

    async def obtener(self) -> Tarifa | None:
        return self._tarifa

    async def guardar(self, tarifa: Tarifa) -> None:
        self._tarifa = tarifa


class FakeCotizacionRepository:
    """Guarda la cotización activa de cada cliente en un dict en memoria."""

    def __init__(self) -> None:
        self._por_cliente: dict[str, Cotizacion] = {}

    async def reemplazar(self, cotizacion: Cotizacion) -> None:
        self._por_cliente[cotizacion.cliente_id] = cotizacion

    async def obtener_activa(self, cliente_id: str) -> Cotizacion:
        cotizacion = self._por_cliente.get(cliente_id)
        if cotizacion is None:
            raise RecursoNoEncontrado("el cliente no tiene una cotización activa")
        return cotizacion

    async def eliminar_activa(self, cliente_id: str) -> None:
        if self._por_cliente.pop(cliente_id, None) is None:
            raise RecursoNoEncontrado("el cliente no tiene una cotización activa")
