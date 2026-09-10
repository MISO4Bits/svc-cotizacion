from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas import SolicitudCotizacionIn

VALIDA = {
    "ramo": "PROTECCION_DISPOSITIVO",
    "canal": {"tipo": "SOCIO", "socioId": "banco-x"},
    "dispositivo": {"tipo": "CELULAR", "valorAsegurado": 3000000, "antiguedadMeses": 8},
    "solicitante": {"edad": 28, "pais": "CO"},
}


def test_solicitud_valida():
    s = SolicitudCotizacionIn.model_validate(VALIDA)
    assert s.canal.socio_id == "banco-x"


@pytest.mark.parametrize(
    "override",
    [
        {"ramo": "OTRO"},
        {"solicitante": {"edad": 17, "pais": "CO"}},
        {"dispositivo": {"tipo": "CELULAR", "valorAsegurado": -1, "antiguedadMeses": 8}},
        {"dispositivo": {"tipo": "RELOJ", "valorAsegurado": 100, "antiguedadMeses": 1}},
        {"sobra": 1},
    ],
)
def test_solicitud_invalida(override):
    with pytest.raises(ValidationError):
        SolicitudCotizacionIn.model_validate({**VALIDA, **override})
