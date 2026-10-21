from __future__ import annotations

HEADERS = {"X-Cliente-Id": "cli-123"}

SOLICITUD_VALIDA = {
    "edad": 38,
    "datosCredito": {
        "valorCredito": 150000000,
        "plazoRestanteMeses": 240,
        "entidadAcreedora": "Banco X",
        "saldoInsoluto": 140000000,
    },
}


def _solicitud(**cambios) -> dict:
    return {**SOLICITUD_VALIDA, **cambios}


def _con_credito(**cambios) -> dict:
    return _solicitud(datosCredito={**SOLICITUD_VALIDA["datosCredito"], **cambios})


async def test_crear_cotizacion_devuelve_201_sin_id(client):
    resp = await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)

    assert resp.status_code == 201
    cuerpo = resp.json()
    assert "id" not in cuerpo
    assert cuerpo["estado"] == "VIGENTE"
    assert cuerpo["producto"] == "VIDA_HIPOTECARIO"
    assert cuerpo["origenDatos"] == "DECLARADO"
    assert cuerpo["oferta"]["personalizado"] is True
    assert cuerpo["oferta"]["primaMensual"] > 0
    assert "perfilRiesgo" in cuerpo


async def test_la_respuesta_trae_los_datos_del_credito_para_mostrarlos(client):
    cuerpo = (await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)).json()

    assert cuerpo["datosCredito"] == {
        "valorCredito": 150000000,
        "plazoRestanteMeses": 240,
        "entidadAcreedora": "Banco X",
        "saldoInsoluto": 140000000,
    }
    assert cuerpo["oferta"]["sumaAsegurada"] == 140000000
    assert cuerpo["oferta"]["coberturaMeses"] == 240


async def test_la_prima_sale_de_la_tabla_de_la_historia(client):
    # 37 años, $178.500.000, 165 meses: la prima base de la historia es $34.986
    # y con el factor 0,90 del perfil simulado queda en $31.487.
    resp = await client.post(
        "/v1/cotizaciones",
        json={
            "edad": 37,
            "datosCredito": {
                "valorCredito": 200000000,
                "plazoRestanteMeses": 165,
                "entidadAcreedora": "Banco X",
                "saldoInsoluto": 178500000,
            },
        },
        headers=HEADERS,
    )

    oferta = resp.json()["oferta"]
    assert oferta["primaBaseMensual"] == 34986
    assert oferta["primaMensual"] == 31487


async def test_consultar_la_activa_devuelve_la_que_se_creo(client):
    creada = (await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)).json()

    resp = await client.get("/v1/cotizaciones/actual", headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json() == creada


async def test_sin_cotizacion_la_activa_devuelve_404(client):
    resp = await client.get("/v1/cotizaciones/actual", headers=HEADERS)

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_eliminar_la_activa_devuelve_204_y_deja_al_cliente_sin_cotizacion(client):
    await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)

    resp = await client.delete("/v1/cotizaciones/actual", headers=HEADERS)

    assert resp.status_code == 204
    assert resp.content == b""
    assert (await client.get("/v1/cotizaciones/actual", headers=HEADERS)).status_code == 404


async def test_eliminar_sin_cotizacion_devuelve_404(client):
    resp = await client.delete("/v1/cotizaciones/actual", headers=HEADERS)

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_eliminar_dos_veces_la_segunda_devuelve_404(client):
    await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    await client.delete("/v1/cotizaciones/actual", headers=HEADERS)

    resp = await client.delete("/v1/cotizaciones/actual", headers=HEADERS)

    assert resp.status_code == 404


async def test_eliminar_la_activa_no_toca_la_de_otro_cliente(client):
    await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers={"X-Cliente-Id": "otro"})

    await client.delete("/v1/cotizaciones/actual", headers=HEADERS)

    resp = await client.get("/v1/cotizaciones/actual", headers={"X-Cliente-Id": "otro"})
    assert resp.status_code == 200


async def test_eliminar_sin_cliente_devuelve_400(client):
    resp = await client.delete("/v1/cotizaciones/actual")

    assert resp.status_code == 400


async def test_una_cotizacion_nueva_reemplaza_a_la_anterior(client):
    await client.post(
        "/v1/cotizaciones", json=_con_credito(saldoInsoluto=100000000), headers=HEADERS
    )
    nueva = await client.post(
        "/v1/cotizaciones", json=_con_credito(saldoInsoluto=200000000), headers=HEADERS
    )

    activa = (await client.get("/v1/cotizaciones/actual", headers=HEADERS)).json()

    assert activa == nueva.json()
    assert activa["datosCredito"]["saldoInsoluto"] == 200000000


async def test_la_cotizacion_activa_es_de_cada_cliente(client):
    await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)

    resp = await client.get("/v1/cotizaciones/actual", headers={"X-Cliente-Id": "otro"})

    assert resp.status_code == 404


async def test_la_ruta_por_id_ya_no_existe(client):
    resp = await client.get("/v1/cotizaciones/abc-123", headers=HEADERS)

    assert resp.status_code == 404


async def test_las_rutas_sin_version_ya_no_existen(client):
    assert (
        await client.post("/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)
    ).status_code == 404


async def test_edad_fuera_de_rango_devuelve_400_con_el_campo_y_el_rango(client):
    resp = await client.post("/v1/cotizaciones", json=_solicitud(edad=70), headers=HEADERS)

    assert resp.status_code == 400
    assert resp.json()["errores"] == [{"campo": "edad", "mensaje": "Debe estar entre 18 y 65 años"}]


async def test_el_credito_que_termina_despues_de_los_75_anos_devuelve_400(client):
    resp = await client.post(
        "/v1/cotizaciones",
        json={**_con_credito(plazoRestanteMeses=240, saldoInsoluto=150000000), "edad": 60},
        headers=HEADERS,
    )

    assert resp.status_code == 400
    assert resp.json()["errores"][0]["campo"] == "datosCredito.plazoRestanteMeses"


async def test_la_solicitud_con_cuestionario_de_habitos_se_rechaza(client):
    resp = await client.post(
        "/v1/cotizaciones",
        json=_solicitud(cuestionarioHabitos={"consumeTabaco": False}),
        headers=HEADERS,
    )

    assert resp.status_code == 400


async def test_campo_del_credito_invalido_devuelve_400(client):
    resp = await client.post(
        "/v1/cotizaciones", json=_con_credito(valorCredito=5_000_000), headers=HEADERS
    )

    assert resp.status_code == 400
    assert resp.json()["errores"]


async def test_sin_header_cliente_devuelve_400(client):
    resp = await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA)

    assert resp.status_code == 400


async def test_la_oferta_trae_el_desglose_con_vida_y_hogar(client):
    resp = await client.post(
        "/v1/cotizaciones", json=_con_credito(valorCredito=320000000), headers=HEADERS
    )

    oferta = resp.json()["oferta"]
    vida, hogar = oferta["desglose"]["coberturas"]
    assert vida == {
        "codigo": "VIDA",
        "obligatoria": True,
        "sumaAsegurada": oferta["sumaAsegurada"],
        "primaNeta": oferta["primaMensual"],
        "iva": 0,
        "primaTotal": oferta["primaMensual"],
    }
    assert hogar == {
        "codigo": "HOGAR",
        "obligatoria": False,
        "sumaAsegurada": 240000000,
        "primaNeta": 23760,
        "iva": 4514,
        "primaTotal": 28274,
    }
    assert set(oferta["desglose"]) == {"coberturas"}


async def test_la_activa_devuelve_el_mismo_desglose(client):
    creada = (await client.post("/v1/cotizaciones", json=SOLICITUD_VALIDA, headers=HEADERS)).json()

    actual = (await client.get("/v1/cotizaciones/actual", headers=HEADERS)).json()

    assert actual["oferta"]["desglose"] == creada["oferta"]["desglose"]
