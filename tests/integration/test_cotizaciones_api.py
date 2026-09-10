from __future__ import annotations

SOLICITUD_VALIDA = {
    "ramo": "PROTECCION_DISPOSITIVO",
    "canal": {"tipo": "SOCIO", "socioId": "banco-x"},
    "dispositivo": {"tipo": "CELULAR", "valorAsegurado": 3000000, "antiguedadMeses": 8},
    "solicitante": {"edad": 28, "pais": "CO"},
}


async def test_crear_cotizacion_devuelve_201(client):
    resp = await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA)
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["estado"] == "VIGENTE"
    assert cuerpo["ramo"] == "PROTECCION_DISPOSITIVO"
    assert cuerpo["prima"]["total"] > 0
    assert len(cuerpo["coberturas"]) >= 1
    assert cuerpo["vigenciaCotizacion"]["hasta"] > cuerpo["vigenciaCotizacion"]["desde"]


async def test_cuerpo_invalido_devuelve_400(client):
    malo = {**SOLICITUD_VALIDA, "solicitante": {"edad": 5, "pais": "CO"}}
    resp = await client.post("/v1/cotizaciones", json=malo)
    assert resp.status_code == 400
    assert resp.json()["errores"]


async def test_campo_extra_devuelve_400(client):
    resp = await client.post("/v1/cotizaciones", json={**SOLICITUD_VALIDA, "sobra": 1})
    assert resp.status_code == 400
