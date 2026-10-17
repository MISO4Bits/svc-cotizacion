from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.adapters.fakes import TARIFA_SEMILLA
from app.domain import (
    CotError,
    DependenciaNoDisponible,
    EstadoCotizacion,
    Moneda,
    Oferta,
    RecursoNoEncontrado,
    ReglaNegocio,
    SolicitudInvalida,
    Vigencia,
)
from tests.factories import cotizacion, perfil, solicitud


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (CotError, 500),
        (SolicitudInvalida, 400),
        (RecursoNoEncontrado, 404),
        (ReglaNegocio, 422),
        (DependenciaNoDisponible, 503),
    ],
)
def test_errores_exponen_status_title_y_detail(error, status):
    exc = error("detalle")
    assert exc.status == status
    assert exc.title
    assert exc.detail == "detalle"
    assert exc.errores == []


def test_error_usa_title_por_defecto():
    exc = SolicitudInvalida()
    assert str(exc) == SolicitudInvalida.title
    assert exc.detail is None


def test_error_lleva_el_detalle_por_campo():
    exc = SolicitudInvalida("x", errores=[{"campo": "edad", "mensaje": "fuera de rango"}])
    assert exc.errores == [{"campo": "edad", "mensaje": "fuera de rango"}]


def test_solicitud_se_construye_con_la_edad_ya_calculada():
    s = solicitud(edad=38)
    assert s.cliente_id == "cli-1"
    assert s.edad == 38
    assert s.datos_credito.plazo_restante_meses == 240


def _oferta(*, personalizado: bool = True, prima: str = "50000", base: str = "60000") -> Oferta:
    return Oferta(
        prima_mensual=Decimal(prima),
        prima_base_mensual=Decimal(base),
        suma_asegurada=Decimal("140000000"),
        cobertura_meses=240,
        moneda=Moneda.COP,
        personalizado=personalizado,
    )


def test_oferta_personalizada_camino_feliz():
    assert _oferta().moneda == "COP"


def test_oferta_sin_personalizar_exige_prima_igual_a_base():
    _oferta(personalizado=False, prima="60000", base="60000")
    with pytest.raises(ReglaNegocio):
        _oferta(personalizado=False, prima="50000", base="60000")


def test_oferta_rechaza_montos_negativos():
    with pytest.raises(ReglaNegocio):
        Oferta(
            prima_mensual=Decimal("-1"),
            prima_base_mensual=Decimal("-1"),
            suma_asegurada=Decimal("0"),
            cobertura_meses=12,
            moneda=Moneda.COP,
            personalizado=False,
        )


def test_vigencia_exige_desde_antes_de_hasta():
    ahora = datetime.now(UTC)
    Vigencia(ahora, ahora + timedelta(days=30))
    with pytest.raises(ReglaNegocio):
        Vigencia(ahora, ahora)


def test_cotizacion_personalizada_camino_feliz():
    c = cotizacion(personalizado=True)
    assert c.producto == "VIDA_HIPOTECARIO"
    assert c.perfil_riesgo == perfil()


def test_cotizacion_no_personalizada_camino_feliz():
    assert cotizacion(personalizado=False).perfil_riesgo is None


def test_cotizacion_personalizada_sin_perfil_falla():
    base = cotizacion(personalizado=True)
    with pytest.raises(ReglaNegocio):
        type(base)(**{**base.__dict__, "perfil_riesgo": None})


def test_cotizacion_no_personalizada_con_perfil_falla():
    base = cotizacion(personalizado=False)
    with pytest.raises(ReglaNegocio):
        type(base)(**{**base.__dict__, "perfil_riesgo": perfil()})


def test_la_cotizacion_esta_vigente_durante_30_dias_y_despues_expirada():
    creada = datetime(2026, 10, 16, tzinfo=UTC)
    c = cotizacion(creada_en=creada)

    assert c.estado_en(creada) == EstadoCotizacion.VIGENTE
    assert c.estado_en(creada + timedelta(days=29, hours=23)) == EstadoCotizacion.VIGENTE
    assert c.estado_en(creada + timedelta(days=30)) == EstadoCotizacion.EXPIRADA
    assert c.estado_en(creada + timedelta(days=90)) == EstadoCotizacion.EXPIRADA


@pytest.mark.parametrize(
    ("edad", "tasa"),
    [
        (18, "0.062"),
        (24, "0.062"),
        (25, "0.095"),
        (30, "0.137"),
        (37, "0.196"),
        (45, "0.402"),
        (52, "0.576"),
        (59, "0.826"),
        (60, "1.184"),
        (65, "1.184"),
    ],
)
def test_la_tarifa_da_la_tasa_de_la_franja_de_la_edad(edad, tasa):
    assert TARIFA_SEMILLA.tasa_para(edad) == Decimal(tasa)


@pytest.mark.parametrize("edad", [17, 66])
def test_la_tarifa_sin_franja_para_la_edad_falla(edad):
    with pytest.raises(ReglaNegocio):
        TARIFA_SEMILLA.tasa_para(edad)
