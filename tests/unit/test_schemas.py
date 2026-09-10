from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import SolicitudCotizacionIn

VALIDA = {
    "datosCredito": {
        "valorCredito": 150000000,
        "plazoMeses": 240,
        "edad": 38,
        "entidadAcreedora": "Banco X",
        "saldoInsoluto": 140000000,
    },
    "cuestionarioHabitos": {
        "consumeTabaco": False,
        "actividadFisica": "REGULAR",
        "condicionesPreexistentes": False,
        "dependientesEconomicos": 2,
    },
}


def test_solicitud_valida():
    s = SolicitudCotizacionIn.model_validate(VALIDA)
    assert s.datos_credito.edad == 38
    assert s.cuestionario_habitos.actividad_fisica == "REGULAR"


@pytest.mark.parametrize(
    "patch",
    [
        {"datosCredito": {**VALIDA["datosCredito"], "edad": 70}},
        {"datosCredito": {**VALIDA["datosCredito"], "valorCredito": 5_000_000}},
        {"datosCredito": {**VALIDA["datosCredito"], "plazoMeses": 6}},
        {"cuestionarioHabitos": {**VALIDA["cuestionarioHabitos"], "actividadFisica": "A_VECES"}},
        {"cuestionarioHabitos": {**VALIDA["cuestionarioHabitos"], "dependientesEconomicos": -1}},
        {"sobra": 1},
    ],
)
def test_solicitud_invalida(patch):
    with pytest.raises(ValidationError):
        SolicitudCotizacionIn.model_validate({**VALIDA, **patch})
