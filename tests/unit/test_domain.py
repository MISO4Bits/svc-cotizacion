from __future__ import annotations

import pytest

from app.domain import (
    CotError,
    DependenciaNoDisponible,
    RecursoNoEncontrado,
    ReglaNegocio,
    SolicitudInvalida,
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


def test_error_usa_title_como_mensaje_por_defecto():
    exc = SolicitudInvalida()
    assert str(exc) == SolicitudInvalida.title
    assert exc.detail is None
