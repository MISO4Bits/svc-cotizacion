from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.perfilador_client import PerfiladorClient
from app.domain import DependenciaNoDisponible, NivelRiesgo
from app.resilience import ResilientHttpClient, build_breaker

BASE = "http://perfilamiento.local"

_RESPUESTA_OK = {
    "nivelRiesgo": "BAJO",
    "factorAjuste": 0.9,
    "factores": [
        {"descripcion": "Actividad física regular", "efecto": "POSITIVO", "pesoRelativo": 0.2}
    ],
    "fuentesNoDisponibles": [],
}


def _cliente(retries: int = 0) -> PerfiladorClient:
    http = ResilientHttpClient(
        BASE,
        breaker=build_breaker("perfilamiento", fail_max=5, reset_timeout=30),
        timeout=0.2,
        retries=retries,
    )
    return PerfiladorClient(http)


@respx.mock
async def test_perfil_camino_feliz():
    respx.get(f"{BASE}/perfiles/cli-1").mock(return_value=httpx.Response(200, json=_RESPUESTA_OK))
    cliente = _cliente()
    try:
        perfil = await cliente.obtener_perfil("cli-1")
    finally:
        await cliente.aclose()
    assert perfil.nivel_riesgo == NivelRiesgo.BAJO
    assert perfil.factor_ajuste == Decimal("0.9")
    assert perfil.factores[0].descripcion == "Actividad física regular"


@respx.mock
async def test_perfil_no_encontrado_devuelve_none():
    respx.get(f"{BASE}/perfiles/cli-1").mock(return_value=httpx.Response(404))
    cliente = _cliente()
    try:
        perfil = await cliente.obtener_perfil("cli-1")
    finally:
        await cliente.aclose()
    assert perfil is None


@respx.mock
async def test_perfil_parcial_sin_pesos():
    respuesta = {
        "nivelRiesgo": "MEDIO",
        "factorAjuste": 1.1,
        "factores": [{"descripcion": "Perfil parcial", "efecto": "NEGATIVO"}],
        "fuentesNoDisponibles": ["open-data"],
    }
    respx.get(f"{BASE}/perfiles/cli-1").mock(return_value=httpx.Response(200, json=respuesta))
    cliente = _cliente()
    try:
        perfil = await cliente.obtener_perfil("cli-1")
    finally:
        await cliente.aclose()
    assert perfil.factores[0].peso_relativo is None
    assert perfil.fuentes_no_disponibles == ("open-data",)


@respx.mock
async def test_perfil_5xx_lanza_dependencia_no_disponible():
    respx.get(f"{BASE}/perfiles/cli-1").mock(return_value=httpx.Response(500))
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.obtener_perfil("cli-1")
    finally:
        await cliente.aclose()


@respx.mock
async def test_perfil_timeout_lanza_dependencia_no_disponible():
    respx.get(f"{BASE}/perfiles/cli-1").mock(side_effect=httpx.ReadTimeout("lento"))
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.obtener_perfil("cli-1")
    finally:
        await cliente.aclose()
