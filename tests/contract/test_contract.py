"""Pruebas de contrato: estructura de ``openapi/openapi.yaml`` y que el servicio lo publica.

La verificación estricta "el código expone exactamente las operaciones del contrato"
se completa en B5, cuando exista la ruta ``POST /v1/cotizaciones``.
"""

from __future__ import annotations

import re

from jsonschema import Draft202012Validator

_METODOS = {"get", "post", "put", "patch", "delete"}
_REF = re.compile(r"#/components/schemas/([A-Za-z0-9_]+)")
_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _ops(paths: dict) -> set[tuple[str, str]]:
    return {
        (m.upper(), _PATH_PARAM.sub("{}", p))
        for p, item in paths.items()
        for m in item
        if m.lower() in _METODOS
    }


def test_spec_tiene_estructura_openapi(openapi_spec):
    assert openapi_spec["openapi"].startswith("3.")
    assert "/v1/cotizaciones" in openapi_spec["paths"]
    assert "post" in openapi_spec["paths"]["/v1/cotizaciones"]


def test_todas_las_referencias_de_schema_existen(openapi_spec):
    definidos = set(openapi_spec["components"]["schemas"])
    referenciados = set(_REF.findall(str(openapi_spec)))
    faltan = referenciados - definidos
    assert not faltan, f"$ref sin definir: {faltan}"


def test_cada_schema_es_json_schema_valido(openapi_spec):
    for schema in openapi_spec["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)


def test_el_codigo_no_expone_operaciones_fuera_del_contrato(app, openapi_spec):
    # En B5 esto pasa a ser igualdad estricta (==).
    assert _ops(app.openapi()["paths"]) <= _ops(openapi_spec["paths"])


async def test_el_servicio_publica_el_contrato(client):
    resp = await client.get("/openapi.yaml")
    assert resp.status_code == 200
    assert "openapi" in resp.text
    assert "cotizaciones" in resp.text
