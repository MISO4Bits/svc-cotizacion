"""Adaptadores en memoria. Corren el servicio standalone y sirven de dobles en pruebas."""

from __future__ import annotations

from decimal import Decimal

from app.domain import (
    ActividadFisica,
    Cotizacion,
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    NivelRiesgo,
    PerfilRiesgo,
    RecursoNoEncontrado,
    SolicitudCotizacion,
)


class FakePerfilRiesgo:
    """Perfilador simulado. Con ``disponible=False`` imita a Perfilamiento caído."""

    def __init__(self, *, disponible: bool = True) -> None:
        self._disponible = disponible

    async def perfilar(self, solicitud: SolicitudCotizacion) -> PerfilRiesgo:
        if not self._disponible:
            raise DependenciaNoDisponible("Perfilamiento no responde")

        habitos = solicitud.cuestionario_habitos
        factor = Decimal("1.00")
        factores: list[FactorRiesgo] = []

        if habitos.consume_tabaco:
            factor += Decimal("0.25")
            factores.append(
                FactorRiesgo("Consumo de tabaco", EfectoFactor.NEGATIVO, Decimal("0.4"))
            )
        if habitos.condiciones_preexistentes:
            factor += Decimal("0.20")
            factores.append(
                FactorRiesgo(
                    "Condiciones médicas preexistentes", EfectoFactor.NEGATIVO, Decimal("0.3")
                )
            )
        if habitos.actividad_fisica == ActividadFisica.REGULAR:
            factor -= Decimal("0.10")
            factores.append(FactorRiesgo("Actividad física regular", EfectoFactor.POSITIVO))
        elif habitos.actividad_fisica == ActividadFisica.OCASIONAL:
            factor -= Decimal("0.05")
        if habitos.dependientes_economicos > 2:
            factor += Decimal("0.05")

        factor = min(max(factor, Decimal("0.60")), Decimal("1.80"))
        if factor < Decimal("0.95"):
            nivel = NivelRiesgo.BAJO
        elif factor <= Decimal("1.15"):
            nivel = NivelRiesgo.MEDIO
        else:
            nivel = NivelRiesgo.ALTO

        return PerfilRiesgo(
            nivel_riesgo=nivel,
            factores=tuple(factores),
            factor_ajuste=factor,
        )


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
