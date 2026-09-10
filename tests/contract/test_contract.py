"""Pruebas de contrato: el código cumple ``openapi/openapi.yaml``."""

from __future__ import annotations

import re

from jsonschema import Draft202012Validator

from app.adapters.fakes import FakePerfilRiesgo
from app.services import CotizacionService

_METODOS = {"get", "post", "put", "patch", "delete"}
_REF = re.compile(r"#/components/schemas/([A-Za-z0-9_]+)")
_PATH_PARAM = re.compile(r"\{[^}]+\}")

HEADERS = {"X-Cliente-Id": "cli-123"}

SOLICITUD_VALIDA = {
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


def _ops(paths: dict) -> set[tuple[str, str]]:
    return {
        (m.upper(), _PATH_PARAM.sub("{}", p))
        for p, item in paths.items()
        for m in item
        if m.lower() in _METODOS
    }


def _validar(spec: dict, ref: str, instancia) -> None:
    schema = {"$ref": f"#/components/schemas/{ref}", "components": spec["components"]}
    errores = sorted(Draft202012Validator(schema).iter_errors(instancia), key=str)
    assert not errores, [e.message for e in errores]


def test_spec_tiene_estructura_openapi(openapi_spec):
    assert openapi_spec["openapi"].startswith("3.")
    assert "post" in openapi_spec["paths"]["/cotizaciones"]


def test_referencias_de_schema_existen(openapi_spec):
    definidos = set(openapi_spec["components"]["schemas"])
    assert not set(_REF.findall(str(openapi_spec))) - definidos


def test_cada_schema_es_json_schema_valido(openapi_spec):
    for schema in openapi_spec["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)


def test_contrato_y_codigo_exponen_las_mismas_operaciones(app, openapi_spec):
    assert _ops(app.openapi()["paths"]) == _ops(openapi_spec["paths"])


async def test_respuesta_personalizada_cumple_el_contrato(client, openapi_spec):
    resp = await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    assert resp.status_code == 201
    _validar(openapi_spec, "Cotizacion", resp.json())


async def test_respuesta_degradada_cumple_el_contrato(app, client, openapi_spec):
    app.state.service = CotizacionService(
        FakePerfilRiesgo(disponible=False), app.state.deps.repositorio
    )
    resp = await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["oferta"]["personalizado"] is False
    assert "perfilRiesgo" not in cuerpo
    _validar(openapi_spec, "Cotizacion", cuerpo)


async def test_error_cumple_problem_details(client, openapi_spec):
    resp = await client.post("/cotizaciones", json={}, headers=HEADERS)
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")
    _validar(openapi_spec, "Problema", resp.json())


async def test_el_servicio_publica_el_contrato(client):
    resp = await client.get("/openapi.yaml")
    assert resp.status_code == 200
    assert "cotizaciones" in resp.text
