from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import (
    Canal,
    Cobertura,
    CotError,
    Cotizacion,
    DependenciaNoDisponible,
    Dispositivo,
    EstadoCotizacion,
    PrimaDesglose,
    Ramo,
    RecursoNoEncontrado,
    ReglaNegocio,
    Solicitante,
    SolicitudCotizacion,
    SolicitudInvalida,
    Tarifa,
    TipoCanal,
    TipoDispositivo,
    Vigencia,
)

# --- errores ---


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


def test_error_usa_title_como_mensaje_por_defecto():
    exc = SolicitudInvalida()
    assert str(exc) == SolicitudInvalida.title
    assert exc.detail is None


# --- datos de entrada ---


def _solicitud() -> SolicitudCotizacion:
    return SolicitudCotizacion(
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        canal=Canal(TipoCanal.SOCIO, "banco-x"),
        dispositivo=Dispositivo(TipoDispositivo.CELULAR, Decimal("3000000"), 6),
        solicitante=Solicitante(30, "CO"),
    )


def test_solicitud_se_construye():
    s = _solicitud()
    assert s.ramo == "PROTECCION_DISPOSITIVO"
    assert s.dispositivo.tipo == TipoDispositivo.CELULAR


# --- resultado y sus invariantes ---


def _prima(pura="80000", gastos="10000", impuestos="10000", total="100000") -> PrimaDesglose:
    return PrimaDesglose(Decimal(pura), Decimal(gastos), Decimal(impuestos), Decimal(total))


def test_prima_desglose_camino_feliz():
    p = _prima()
    assert p.total == Decimal("100000")
    assert p.moneda == "COP"


def test_prima_desglose_rechaza_total_inconsistente():
    with pytest.raises(ReglaNegocio):
        _prima(total="123456")


def test_prima_desglose_rechaza_negativos():
    with pytest.raises(ReglaNegocio):
        PrimaDesglose(Decimal("-1"), Decimal("0"), Decimal("0"), Decimal("-1"))


def test_vigencia_exige_desde_antes_de_hasta():
    ahora = datetime.now(UTC)
    Vigencia(ahora, ahora + timedelta(days=15))
    with pytest.raises(ReglaNegocio):
        Vigencia(ahora, ahora)


def _cotizacion(coberturas):
    ahora = datetime.now(UTC)
    return Cotizacion(
        id="cot-1",
        estado=EstadoCotizacion.VIGENTE,
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        prima=_prima(),
        coberturas=coberturas,
        vigencia=Vigencia(ahora, ahora + timedelta(days=15)),
        creada_en=ahora,
    )


def test_cotizacion_camino_feliz():
    cob = Cobertura("ROBO", "Robo y hurto", Decimal("3000000"), Decimal("150000"))
    c = _cotizacion((cob,))
    assert c.estado == EstadoCotizacion.VIGENTE
    assert len(c.coberturas) == 1


def test_cotizacion_exige_al_menos_una_cobertura():
    with pytest.raises(ReglaNegocio):
        _cotizacion(())


def test_tarifa_se_construye():
    cob = Cobertura("ROBO", "Robo y hurto", Decimal("3000000"), Decimal("150000"))
    t = Tarifa(
        ramo=Ramo.PROTECCION_DISPOSITIVO,
        tasa_base_anual=Decimal("0.04"),
        recargo_gastos=Decimal("0.15"),
        tasa_impuesto=Decimal("0.19"),
        coberturas=(cob,),
    )
    assert t.ramo == "PROTECCION_DISPOSITIVO"
    assert t.coberturas[0].codigo == "ROBO"
