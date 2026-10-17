from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import SolicitudCotizacionIn

VALIDA = {
    "edad": 38,
    "datosCredito": {
        "valorCredito": 150000000,
        "plazoRestanteMeses": 240,
        "entidadAcreedora": "Banco X",
        "saldoInsoluto": 140000000,
    },
}


def test_solicitud_valida():
    s = SolicitudCotizacionIn.model_validate(VALIDA)
    assert s.edad == 38
    assert s.datos_credito.plazo_restante_meses == 240


def test_la_edad_fuera_de_rango_pasa_el_esquema_porque_la_valida_el_servicio():
    # El servicio responde con el campo y el rango (18 a 65); ver test_services.
    assert SolicitudCotizacionIn.model_validate({**VALIDA, "edad": 70}).edad == 70


@pytest.mark.parametrize(
    "patch",
    [
        {"datosCredito": {**VALIDA["datosCredito"], "valorCredito": 5_000_000}},
        {"datosCredito": {**VALIDA["datosCredito"], "plazoRestanteMeses": 0}},
        {"datosCredito": {**VALIDA["datosCredito"], "plazoRestanteMeses": 481}},
        {"datosCredito": {**VALIDA["datosCredito"], "saldoInsoluto": 0}},
        {"datosCredito": {**VALIDA["datosCredito"], "entidadAcreedora": "X"}},
        {"edad": "treinta"},
        {"sobra": 1},
        # El cuestionario de hábitos se eliminó: ya no se acepta.
        {"cuestionarioHabitos": {"consumeTabaco": False}},
    ],
)
def test_solicitud_invalida(patch):
    with pytest.raises(ValidationError):
        SolicitudCotizacionIn.model_validate({**VALIDA, **patch})


@pytest.mark.parametrize("campo", ["edad", "datosCredito"])
def test_solicitud_sin_campos_obligatorios(campo):
    incompleta = {k: v for k, v in VALIDA.items() if k != campo}
    with pytest.raises(ValidationError):
        SolicitudCotizacionIn.model_validate(incompleta)
