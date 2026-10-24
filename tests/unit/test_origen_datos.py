"""BITS-101: el origen de los datos del crédito (CONFIRMADO / DECLARADO) y los eventos."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from app.adapters.fakes import FakeCotizacionRepository, FakeEventos, FakeTarifa
from app.adapters.perfilador_client import perfil_a_dict, perfil_desde_dict
from app.domain import (
    DatosCredito,
    DependenciaNoDisponible,
    Hipoteca,
    OrigenDatos,
    PerfilRiesgo,
    clave_entidad,
    coincide_con_hipoteca,
)
from app.services import CotizacionService
from tests.factories import perfil, solicitud

HIPOTECA = Hipoteca("BBVA COLOMBIA S.A.", Decimal("150000000"), Decimal("140000000"), 240)


def _credito(**cambios) -> DatosCredito:
    base = DatosCredito(
        valor_credito=Decimal("150000000"),
        plazo_restante_meses=240,
        entidad_acreedora="BBVA Colombia",
        saldo_insoluto=Decimal("140000000"),
    )
    return replace(base, **cambios)


# --- clave_entidad ---


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [
        ("BBVA COLOMBIA S.A.", "bbva colombia"),
        ("Banco de Bogotá", "banco de bogota"),
        ("BANCO DE BOGOTÁ S.A.", "banco de bogota"),
        ("Davivienda SA", "davivienda"),
        ("  Bancolombia ", "bancolombia"),
    ],
)
def test_clave_entidad_ignora_tildes_mayusculas_puntuacion_y_sufijo(nombre, clave):
    assert clave_entidad(nombre) == clave


# --- coincide_con_hipoteca ---


def test_el_nombre_canonico_coincide_con_el_que_reporta_la_fuente():
    assert coincide_con_hipoteca(_credito(), (HIPOTECA,))


@pytest.mark.parametrize(
    "cambio",
    [
        {"entidad_acreedora": "Davivienda"},
        {"valor_credito": Decimal("150000001")},
        {"saldo_insoluto": Decimal("139999999")},
        {"plazo_restante_meses": 239},
    ],
)
def test_cualquier_diferencia_impide_la_coincidencia(cambio):
    assert not coincide_con_hipoteca(_credito(**cambio), (HIPOTECA,))


def test_sin_hipotecas_no_hay_coincidencia():
    assert not coincide_con_hipoteca(_credito(), ())


def test_basta_con_que_coincida_una_de_varias():
    otra = Hipoteca("DAVIVIENDA S.A.", Decimal("90000000"), Decimal("41000000"), 54)
    assert coincide_con_hipoteca(_credito(), (otra, HIPOTECA))


# --- el servicio ---


class _Perfilador:
    def __init__(self, resultado) -> None:
        self._resultado = resultado

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        if isinstance(self._resultado, Exception):
            raise self._resultado
        return self._resultado


def _servicio(resultado, eventos=None) -> CotizacionService:
    return CotizacionService(
        _Perfilador(resultado),
        FakeTarifa(),
        FakeCotizacionRepository(),
        eventos or FakeEventos(),
    )


async def test_con_el_credito_reportado_por_open_finance_queda_confirmado():
    servicio = _servicio(replace(perfil(), hipotecas=(HIPOTECA,)))

    cot = await servicio.crear_cotizacion(replace(solicitud(), datos_credito=_credito()))

    assert cot.origen_datos is OrigenDatos.CONFIRMADO


async def test_con_datos_distintos_a_los_reportados_queda_declarado():
    servicio = _servicio(replace(perfil(), hipotecas=(HIPOTECA,)))

    cot = await servicio.crear_cotizacion(
        replace(solicitud(), datos_credito=_credito(saldo_insoluto=Decimal("130000000")))
    )

    assert cot.origen_datos is OrigenDatos.DECLARADO


@pytest.mark.parametrize("resultado", [perfil(), None, DependenciaNoDisponible("caído")])
async def test_sin_hipotecas_a_la_vista_queda_declarado(resultado):
    cot = await _servicio(resultado).crear_cotizacion(
        replace(solicitud(), datos_credito=_credito())
    )

    assert cot.origen_datos is OrigenDatos.DECLARADO


# --- eventos ---


async def test_crear_una_cotizacion_publica_cotizacion_creada():
    eventos = FakeEventos()

    cot = await _servicio(perfil(), eventos).crear_cotizacion(solicitud())

    assert [e.tipo for e in eventos.publicados] == ["CotizacionCreada"]
    assert eventos.publicados[0].datos == {
        "clienteId": "cli-1",
        "creadaEn": cot.creada_en.isoformat(),
    }


async def test_eliminar_la_activa_publica_cotizacion_eliminada():
    eventos = FakeEventos()
    servicio = _servicio(perfil(), eventos)
    await servicio.crear_cotizacion(solicitud())

    await servicio.eliminar_cotizacion_activa("cli-1")

    assert [e.tipo for e in eventos.publicados] == ["CotizacionCreada", "CotizacionEliminada"]
    assert eventos.publicados[1].datos == {"clienteId": "cli-1"}


async def test_si_no_se_puede_publicar_la_cotizacion_igual_se_crea():
    servicio = _servicio(perfil(), FakeEventos(falla=True))

    cot = await servicio.crear_cotizacion(solicitud())
    activa = await servicio.obtener_cotizacion_activa("cli-1")

    assert activa == cot


# --- el perfil que viaja por la red y por el caché ---


def test_las_hipotecas_viajan_en_el_perfil_y_vuelven_iguales():
    con_hipotecas = replace(perfil(), hipotecas=(HIPOTECA,))

    de_vuelta = perfil_desde_dict(json.loads(json.dumps(perfil_a_dict(con_hipotecas))))

    assert de_vuelta.hipotecas == (HIPOTECA,)


def test_perfilamiento_las_manda_como_numeros():
    recibido = perfil_desde_dict(
        {
            "nivelRiesgo": "BAJO",
            "factorAjuste": 0.9,
            "factores": [],
            "hipotecas": [
                {
                    "entidadAcreedora": "BBVA COLOMBIA S.A.",
                    "valorCredito": 150000000.0,
                    "saldoInsoluto": 140000000,
                    "plazoRestanteMeses": 240,
                    "cuotaMensual": 2100000,
                }
            ],
        }
    )

    assert recibido.hipotecas == (HIPOTECA,)


def test_un_perfil_guardado_antes_sin_hipotecas_se_lee_sin_ellas():
    antiguo = perfil_desde_dict({"nivelRiesgo": "BAJO", "factorAjuste": "0.9", "factores": []})

    assert antiguo.hipotecas == ()
