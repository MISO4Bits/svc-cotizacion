"""Cliente de Productos y caché cache-aside de la tarifa."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.fakes import TARIFA_SEMILLA, FakeTarifa, FakeTarifaCache
from app.adapters.tarifa_cache import TarifaCacheada
from app.adapters.tarifa_client import TarifaClient, tarifa_a_dict, tarifa_desde_dict
from app.domain import DependenciaNoDisponible
from app.resilience import ResilientHttpClient, build_breaker

BASE = "http://productos.test"

_RESPUESTA = {
    "mercado": "CO",
    "producto": "VIDA_HIPOTECARIO",
    "version": 3,
    "franjas": [
        {"edadDesde": 18, "edadHasta": 40, "tasaMensualPorMil": 0.1},
        {"edadDesde": 41, "edadHasta": 65, "tasaMensualPorMil": 0.9},
    ],
}


def _cliente() -> TarifaClient:
    http = ResilientHttpClient(
        BASE, breaker=build_breaker("productos-test", fail_max=5, reset_timeout=30), timeout=1.0
    )
    return TarifaClient(http)


@respx.mock
async def test_el_cliente_pide_la_tarifa_del_mercado_y_la_parsea():
    ruta = respx.get(f"{BASE}/v1/tarifas/vida-hipotecario", params={"mercado": "CO"}).mock(
        return_value=httpx.Response(200, json=_RESPUESTA)
    )
    cliente = _cliente()
    try:
        tarifa = await cliente.obtener()
    finally:
        await cliente.aclose()

    assert ruta.called
    assert tarifa.version == 3
    assert tarifa.tasa_para(30) == Decimal("0.1")
    assert tarifa.tasa_para(50) == Decimal("0.9")


@respx.mock
@pytest.mark.parametrize("respuesta", [httpx.Response(404), httpx.Response(400)])
async def test_una_respuesta_de_error_es_dependencia_no_disponible(respuesta):
    respx.get(f"{BASE}/v1/tarifas/vida-hipotecario").mock(return_value=respuesta)
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.obtener()
    finally:
        await cliente.aclose()


@respx.mock
async def test_un_timeout_es_dependencia_no_disponible():
    respx.get(f"{BASE}/v1/tarifas/vida-hipotecario").mock(side_effect=httpx.ReadTimeout("lento"))
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.obtener()
    finally:
        await cliente.aclose()


def test_la_tarifa_se_serializa_y_se_lee_igual_para_el_cache():
    assert tarifa_desde_dict(tarifa_a_dict(TARIFA_SEMILLA)) == TARIFA_SEMILLA


async def test_la_primera_vez_llama_a_productos_y_las_siguientes_salen_del_cache():
    interno = FakeTarifa()
    cache = FakeTarifaCache()
    tarifa = TarifaCacheada(interno, cache)

    primera = await tarifa.obtener()
    segunda = await tarifa.obtener()
    tercera = await tarifa.obtener()

    assert primera == segunda == tercera == TARIFA_SEMILLA
    assert interno.llamadas == 1
    assert await cache.obtener() == TARIFA_SEMILLA


async def test_con_el_cache_vacio_varias_cotizaciones_hacen_una_sola_llamada():
    class _Lenta(FakeTarifa):
        async def obtener(self):
            await asyncio.sleep(0.01)
            return await super().obtener()

    interno = _Lenta()
    tarifa = TarifaCacheada(interno, FakeTarifaCache())

    resultados = await asyncio.gather(*(tarifa.obtener() for _ in range(20)))

    assert interno.llamadas == 1
    assert all(r == TARIFA_SEMILLA for r in resultados)


async def test_con_productos_caido_y_sin_cache_falla_y_no_guarda_nada():
    cache = FakeTarifaCache()
    tarifa = TarifaCacheada(FakeTarifa(disponible=False), cache)

    with pytest.raises(DependenciaNoDisponible):
        await tarifa.obtener()

    assert await cache.obtener() is None


async def test_con_la_tarifa_en_cache_no_depende_de_productos():
    cache = FakeTarifaCache()
    await cache.guardar(TARIFA_SEMILLA)
    interno = FakeTarifa(disponible=False)

    assert await TarifaCacheada(interno, cache).obtener() == TARIFA_SEMILLA
    assert interno.llamadas == 0


async def test_aclose_cierra_el_cliente_interno():
    class _Cerrable(FakeTarifa):
        cerrado = False

        async def aclose(self):
            self.cerrado = True

    interno = _Cerrable()
    await TarifaCacheada(interno, FakeTarifaCache()).aclose()

    assert interno.cerrado
