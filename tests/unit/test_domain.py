from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import (
    ActividadFisica,
    CotError,
    Cotizacion,
    CuestionarioHabitos,
    DatosCredito,
    DependenciaNoDisponible,
    EfectoFactor,
    EstadoCotizacion,
    FactorRiesgo,
    Moneda,
    NivelRiesgo,
    Oferta,
    PerfilRiesgo,
    RecursoNoEncontrado,
    ReglaNegocio,
    SolicitudCotizacion,
    SolicitudInvalida,
    Vigencia,
)


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


def test_error_usa_title_por_defecto():
    exc = SolicitudInvalida()
    assert str(exc) == SolicitudInvalida.title
    assert exc.detail is None


def test_solicitud_se_construye():
    s = SolicitudCotizacion(
        cliente_id="cli-1",
        datos_credito=DatosCredito(
            valor_credito=Decimal("150000000"),
            plazo_meses=240,
            edad=38,
            entidad_acreedora="Banco X",
            saldo_insoluto=Decimal("140000000"),
        ),
        cuestionario_habitos=CuestionarioHabitos(
            consume_tabaco=False,
            actividad_fisica=ActividadFisica.REGULAR,
            condiciones_preexistentes=False,
            dependientes_economicos=2,
        ),
    )
    assert s.cliente_id == "cli-1"
    assert s.cuestionario_habitos.actividad_fisica == "REGULAR"


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


def _perfil() -> PerfilRiesgo:
    return PerfilRiesgo(
        nivel_riesgo=NivelRiesgo.BAJO,
        factores=(FactorRiesgo("Actividad física regular", EfectoFactor.POSITIVO),),
        factor_ajuste=Decimal("0.9"),
    )


def _cotizacion(*, personalizado: bool, perfil: PerfilRiesgo | None) -> Cotizacion:
    ahora = datetime.now(UTC)
    oferta = (
        _oferta() if personalizado else _oferta(personalizado=False, prima="60000", base="60000")
    )
    return Cotizacion(
        id="cot-1",
        cliente_id="cli-1",
        estado=EstadoCotizacion.VIGENTE,
        oferta=oferta,
        perfil_riesgo=perfil,
        vigencia=Vigencia(ahora, ahora + timedelta(days=30)),
        creada_en=ahora,
    )


def test_cotizacion_personalizada_camino_feliz():
    c = _cotizacion(personalizado=True, perfil=_perfil())
    assert c.producto == "VIDA_HIPOTECARIO"


def test_cotizacion_no_personalizada_camino_feliz():
    assert _cotizacion(personalizado=False, perfil=None).perfil_riesgo is None


def test_cotizacion_personalizada_sin_perfil_falla():
    with pytest.raises(ReglaNegocio):
        _cotizacion(personalizado=True, perfil=None)


def test_cotizacion_no_personalizada_con_perfil_falla():
    with pytest.raises(ReglaNegocio):
        _cotizacion(personalizado=False, perfil=_perfil())
