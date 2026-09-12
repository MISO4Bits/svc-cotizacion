from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.perfilador_client import PerfiladorClient
from app.domain import (
    ActividadFisica,
    CuestionarioHabitos,
    DatosCredito,
    DependenciaNoDisponible,
    NivelRiesgo,
    SolicitudCotizacion,
)
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


def _solicitud() -> SolicitudCotizacion:
    return SolicitudCotizacion(
        cliente_id="cli-1",
        datos_credito=DatosCredito(
            valor_credito=Decimal("150000000"),
            plazo_meses=240,
            edad=38,
            entidad_acreedora="Banco X",
            saldo_insoluto=Decimal("140000000"),
        ),
        cuestionario_habitos=CuestionarioHabitos(
            consume_tabaco=False,
            actividad_fisica=ActividadFisica.REGULAR,
            condiciones_preexistentes=False,
            dependientes_economicos=1,
        ),
    )


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
    respx.post(f"{BASE}/perfiles").mock(return_value=httpx.Response(200, json=_RESPUESTA_OK))
    cliente = _cliente()
    try:
        perfil = await cliente.perfilar(_solicitud())
    finally:
        await cliente.aclose()
    assert perfil.nivel_riesgo == NivelRiesgo.BAJO
    assert perfil.factor_ajuste == Decimal("0.9")
    assert perfil.factores[0].descripcion == "Actividad física regular"


@respx.mock
async def test_perfil_envia_credito_y_cuestionario():
    ruta = respx.post(f"{BASE}/perfiles").mock(return_value=httpx.Response(200, json=_RESPUESTA_OK))
    cliente = _cliente()
    try:
        await cliente.perfilar(_solicitud())
    finally:
        await cliente.aclose()
    cuerpo = json.loads(ruta.calls.last.request.content)
    assert cuerpo["clienteId"] == "cli-1"
    assert cuerpo["datosCredito"]["edad"] == 38
    assert cuerpo["cuestionarioHabitos"]["actividadFisica"] == "REGULAR"


@respx.mock
async def test_perfil_parcial_sin_pesos():
    respuesta = {
        "nivelRiesgo": "MEDIO",
        "factorAjuste": 1.1,
        "factores": [{"descripcion": "Perfil parcial", "efecto": "NEGATIVO"}],
        "fuentesNoDisponibles": ["open-data"],
    }
    respx.post(f"{BASE}/perfiles").mock(return_value=httpx.Response(200, json=respuesta))
    cliente = _cliente()
    try:
        perfil = await cliente.perfilar(_solicitud())
    finally:
        await cliente.aclose()
    assert perfil.factores[0].peso_relativo is None
    assert perfil.fuentes_no_disponibles == ("open-data",)


@respx.mock
async def test_perfil_5xx_lanza_dependencia_no_disponible():
    respx.post(f"{BASE}/perfiles").mock(return_value=httpx.Response(500))
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.perfilar(_solicitud())
    finally:
        await cliente.aclose()


@respx.mock
async def test_perfil_timeout_lanza_dependencia_no_disponible():
    respx.post(f"{BASE}/perfiles").mock(side_effect=httpx.ReadTimeout("lento"))
    cliente = _cliente()
    try:
        with pytest.raises(DependenciaNoDisponible):
            await cliente.perfilar(_solicitud())
    finally:
        await cliente.aclose()
