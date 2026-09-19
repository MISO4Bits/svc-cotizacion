from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain import (
    ActividadFisica,
    Cotizacion,
    CuestionarioHabitos,
    DatosCredito,
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    NivelRiesgo,
    PerfilRiesgo,
    RecursoNoEncontrado,
    SolicitudCotizacion,
)
from app.services import CotizacionService, calcular_prima_base


def _datos(edad: int = 38, saldo: str = "140000000", plazo: int = 240) -> DatosCredito:
    return DatosCredito(
        valor_credito=Decimal("150000000"),
        plazo_meses=plazo,
        edad=edad,
        entidad_acreedora="Banco X",
        saldo_insoluto=Decimal(saldo),
    )


def _solicitud(**kw) -> SolicitudCotizacion:
    return SolicitudCotizacion(
        cliente_id="cli-1",
        datos_credito=_datos(**kw),
        cuestionario_habitos=CuestionarioHabitos(
            consume_tabaco=False,
            actividad_fisica=ActividadFisica.OCASIONAL,
            condiciones_preexistentes=False,
            dependientes_economicos=1,
        ),
    )


class _PerfilOk:
    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo:
        return PerfilRiesgo(
            nivel_riesgo=NivelRiesgo.BAJO,
            factores=(FactorRiesgo("Actividad física regular", EfectoFactor.POSITIVO),),
            factor_ajuste=Decimal("0.90"),
        )


class _PerfilCaido:
    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo:
        raise DependenciaNoDisponible("Perfilamiento no responde")


class _PerfilInexistente:
    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        return None


class _Repo:
    def __init__(self) -> None:
        self.guardadas: list[Cotizacion] = []

    async def guardar(self, cotizacion: Cotizacion) -> None:
        self.guardadas.append(cotizacion)

    async def obtener(self, cotizacion_id: str, cliente_id: str) -> Cotizacion:
        for c in self.guardadas:
            if c.id == cotizacion_id and c.cliente_id == cliente_id:
                return c
        raise RecursoNoEncontrado("no encontrada")


def test_prima_base_escala_con_la_edad():
    assert calcular_prima_base(_datos(edad=30)) < calcular_prima_base(_datos(edad=45))
    assert calcular_prima_base(_datos(edad=45)) < calcular_prima_base(_datos(edad=60))


def test_prima_base_escala_con_el_saldo():
    assert calcular_prima_base(_datos(saldo="100000000")) < calcular_prima_base(
        _datos(saldo="200000000")
    )


async def test_crear_cotizacion_personalizada():
    repo = _Repo()
    cot = await CotizacionService(_PerfilOk(), repo).crear_cotizacion(_solicitud())

    assert cot.oferta.personalizado is True
    assert cot.perfil_riesgo is not None
    assert cot.oferta.prima_mensual < cot.oferta.prima_base_mensual
    assert repo.guardadas == [cot]


async def test_crear_cotizacion_cae_a_tarifa_estandar_si_perfilamiento_falla():
    cot = await CotizacionService(_PerfilCaido(), _Repo()).crear_cotizacion(_solicitud())

    assert cot.oferta.personalizado is False
    assert cot.perfil_riesgo is None
    assert cot.oferta.prima_mensual == cot.oferta.prima_base_mensual
    assert cot.oferta.fuentes_no_disponibles == ("perfilamiento",)


async def test_crear_cotizacion_cae_a_tarifa_estandar_si_perfil_no_existe_todavia():
    """Perfilamiento respondió (no está caído) pero el cliente no tiene
    perfil calculado todavía — mismo fallback que una dependencia caída,
    pero es un camino distinto (None, no excepción)."""
    cot = await CotizacionService(_PerfilInexistente(), _Repo()).crear_cotizacion(_solicitud())

    assert cot.oferta.personalizado is False
    assert cot.perfil_riesgo is None
    assert cot.oferta.fuentes_no_disponibles == ("perfilamiento",)


async def test_obtener_cotizacion():
    service = CotizacionService(_PerfilOk(), _Repo())
    creada = await service.crear_cotizacion(_solicitud())

    assert await service.obtener_cotizacion(creada.id, "cli-1") == creada
    with pytest.raises(RecursoNoEncontrado):
        await service.obtener_cotizacion(creada.id, "otro")
