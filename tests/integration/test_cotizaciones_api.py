from __future__ import annotations

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


async def test_crear_cotizacion_devuelve_201(client):
    resp = await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    assert resp.status_code == 201
    cuerpo = resp.json()
    assert cuerpo["estado"] == "VIGENTE"
    assert cuerpo["producto"] == "VIDA_HIPOTECARIO"
    assert cuerpo["oferta"]["personalizado"] is True
    assert cuerpo["oferta"]["primaMensual"] > 0
    assert "perfilRiesgo" in cuerpo


async def test_crear_y_obtener(client):
    creada = await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    cid = creada.json()["id"]
    resp = await client.get(f"/cotizaciones/{cid}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


async def test_obtener_de_otro_cliente_devuelve_404(client):
    creada = await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    cid = creada.json()["id"]
    resp = await client.get(f"/cotizaciones/{cid}", headers={"X-Cliente-Id": "otro"})
    assert resp.status_code == 404


async def test_campo_fuera_de_rango_devuelve_400(client):
    malo = {**SOLICITUD_VALIDA, "datosCredito": {**SOLICITUD_VALIDA["datosCredito"], "edad": 70}}
    resp = await client.post("/cotizaciones", json=malo, headers=HEADERS)
    assert resp.status_code == 400
    assert resp.json()["errores"]


async def test_sin_header_cliente_devuelve_400(client):
    resp = await client.post("/cotizaciones", json=SOLICITUD_VALIDA)
    assert resp.status_code == 400
