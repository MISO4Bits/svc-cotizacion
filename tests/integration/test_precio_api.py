"""BITS-378: ``POST /v1/cotizaciones/precio``, el precio de un crédito sin cotización."""

from __future__ import annotations

from jsonschema import Draft202012Validator

from app.adapters.fakes import FakeEventos, FakePerfilRiesgo, FakeTarifa
from app.services import CotizacionService

RUTA = "/v1/cotizaciones/precio"
CLIENTE = {"X-Cliente-Id": "cli-123"}
SOLICITUD = {
    "edad": 38,
    "datosCredito": {
        "valorCredito": 150000000,
        "plazoRestanteMeses": 240,
        "entidadAcreedora": "Bancolombia",
        "saldoInsoluto": 150000000,
    },
}


def _validar(spec: dict, ref: str, instancia) -> None:
    schema = {"$ref": f"#/components/schemas/{ref}", "components": spec["components"]}
    errores = sorted(Draft202012Validator(schema).iter_errors(instancia), key=str)
    assert not errores, [e.message for e in errores]


def _con_credito(**cambios) -> dict:
    return {**SOLICITUD, "datosCredito": {**SOLICITUD["datosCredito"], **cambios}}


async def test_el_precio_cumple_el_contrato_y_es_confirmado(client, openapi_spec):
    respuesta = await client.post(RUTA, json=SOLICITUD)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    _validar(openapi_spec, "CotizacionActivaInterna", cuerpo)
    assert cuerpo["origenDatos"] == "CONFIRMADO"
    assert cuerpo["estado"] == "VIGENTE"
    assert cuerpo["edad"] == 38
    assert cuerpo["coberturaMeses"] == 240


async def test_el_precio_trae_vida_obligatoria_y_hogar_opcional(client):
    cuerpo = (await client.post(RUTA, json=SOLICITUD)).json()

    vida, hogar = cuerpo["coberturas"]
    assert (vida["codigo"], vida["obligatoria"], vida["iva"]) == ("VIDA", True, 0)
    assert (hogar["codigo"], hogar["obligatoria"]) == ("HOGAR", False)
    assert vida["sumaAsegurada"] == 150000000  # el crédito es nuevo: el saldo es el monto
    assert vida["primaTotal"] > 0 and hogar["primaTotal"] > hogar["primaNeta"]  # Hogar lleva IVA
    assert hogar["sumaAsegurada"] <= 150000000


async def test_el_precio_es_el_mismo_que_el_de_la_cotizacion_del_autoservicio(client):
    """Misma tarifa y mismas cuentas; lo único que cambia es el perfil de riesgo, que no se usa."""
    precio = (await client.post(RUTA, json=SOLICITUD)).json()
    cotizacion = (await client.post("/v1/cotizaciones", json=SOLICITUD, headers=CLIENTE)).json()
    # La cotización del autoservicio con un perfil que no ajusta la prima base.
    base = cotizacion["oferta"]["primaBaseMensual"]

    assert precio["coberturas"][0]["primaTotal"] == base
    assert precio["tasa"] > 0
    assert precio["versionTarifa"] == (
        await client.get("/v1/cotizaciones/actual", headers=CLIENTE)
    ).json()["oferta"].get("versionTarifa", precio["versionTarifa"])


async def test_calcular_el_precio_no_guarda_nada_ni_publica_eventos(app, client):
    eventos = FakeEventos()
    app.state.service = CotizacionService(
        FakePerfilRiesgo(), FakeTarifa(), app.state.deps.repositorio, eventos
    )

    respuesta = await client.post(RUTA, json=SOLICITUD)

    assert respuesta.status_code == 200
    assert eventos.publicados == []
    assert (await client.get("/v1/cotizaciones/actual", headers=CLIENTE)).status_code == 404


async def test_calcular_el_precio_no_toca_la_cotizacion_activa_de_un_cliente(client):
    propia = {**SOLICITUD, "edad": 50}
    await client.post("/v1/cotizaciones", json=propia, headers=CLIENTE)
    antes = (await client.get("/v1/cotizaciones/actual", headers=CLIENTE)).json()

    await client.post(RUTA, json=SOLICITUD)

    assert (await client.get("/v1/cotizaciones/actual", headers=CLIENTE)).json() == antes


async def test_no_usa_el_perfil_de_riesgo(app, client):
    perfil = FakePerfilRiesgo()
    app.state.service = CotizacionService(
        perfil, FakeTarifa(), app.state.deps.repositorio, FakeEventos()
    )

    await client.post(RUTA, json=SOLICITUD)

    assert not getattr(perfil, "llamadas", 0)


async def test_no_pide_el_encabezado_del_cliente(client):
    assert (await client.post(RUTA, json=SOLICITUD)).status_code == 200


async def test_la_edad_fuera_de_rango_es_400_con_el_campo(client, openapi_spec):
    for edad in (17, 66):
        respuesta = await client.post(RUTA, json={**SOLICITUD, "edad": edad})

        assert respuesta.status_code == 400
        assert respuesta.json()["errores"][0]["campo"] == "edad"
    _validar(openapi_spec, "Problema", respuesta.json())


async def test_un_credito_que_termina_despues_de_los_75_anos_es_400(client):
    # 65 años y 11 años de plazo: termina a los 76.
    respuesta = await client.post(RUTA, json={**_con_credito(plazoRestanteMeses=132), "edad": 65})

    assert respuesta.status_code == 400
    assert respuesta.json()["errores"][0]["campo"] == "datosCredito.plazoRestanteMeses"


async def test_el_borde_de_la_edad_al_terminar_se_acepta(client):
    # 65 años y 10 años de plazo: termina exactamente a los 75.
    respuesta = await client.post(RUTA, json={**_con_credito(plazoRestanteMeses=120), "edad": 65})

    assert respuesta.status_code == 200


async def test_los_limites_del_credito_son_400(client):
    for cambios in (
        {"valorCredito": 9_999_999, "saldoInsoluto": 9_999_999},
        {"plazoRestanteMeses": 0},
        {"plazoRestanteMeses": 481},
        {"entidadAcreedora": "x"},
        {"saldoInsoluto": 0},
    ):
        respuesta = await client.post(RUTA, json=_con_credito(**cambios))
        assert respuesta.status_code == 400, cambios


async def test_un_cuerpo_con_campos_de_mas_o_sin_edad_es_400(client):
    assert (await client.post(RUTA, json={**SOLICITUD, "cuotaMensual": 900000})).status_code == 400
    assert (
        await client.post(RUTA, json={"datosCredito": SOLICITUD["datosCredito"]})
    ).status_code == 400
    assert (await client.post(RUTA, json={})).status_code == 400


async def test_sin_tarifa_responde_503(app, client, openapi_spec):
    app.state.service = CotizacionService(
        FakePerfilRiesgo(), FakeTarifa(disponible=False), app.state.deps.repositorio, FakeEventos()
    )

    respuesta = await client.post(RUTA, json=SOLICITUD)

    assert respuesta.status_code == 503
    _validar(openapi_spec, "Problema", respuesta.json())
