from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.adapters.fakes import TARIFA_SEMILLA, FakeCotizacionRepository, FakeTarifa
from app.domain import (
    CodigoCobertura,
    DependenciaNoDisponible,
    PerfilRiesgo,
    RecursoNoEncontrado,
    SolicitudInvalida,
    TarifaHogar,
)
from app.services import (
    CotizacionService,
    calcular_cobertura_hogar,
    calcular_desglose,
    calcular_prima_base,
    validar_solicitud,
)
from tests.factories import cotizacion, datos_credito, perfil, solicitud


class _PerfilOk:
    def __init__(self, factor: str = "0.90") -> None:
        self._factor = factor

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo:
        return perfil(self._factor)


class _PerfilCaido:
    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo:
        raise DependenciaNoDisponible("Perfilamiento no responde")


class _PerfilInexistente:
    async def obtener_perfil(self, cliente_id: str) -> None:
        return None


def _servicio(perfilador=None, tarifa=None, repositorio=None) -> CotizacionService:
    return CotizacionService(
        perfilador or _PerfilOk(),
        tarifa or FakeTarifa(),
        repositorio or FakeCotizacionRepository(),
    )


# --- los ejemplos de la historia BITS-95 ---
# (edad, saldo, plazo restante, factor, prima base, prima mensual)
EJEMPLOS = [
    (30, "98000000", 96, "0.85", "13426", "11412"),
    (37, "178500000", 165, "1.15", "34986", "40234"),
    (45, "142000000", 228, "1.65", "57084", "94189"),
    (52, "160000000", 180, None, "92160", "92160"),  # sin perfil
]


@pytest.mark.parametrize(("edad", "saldo", "plazo", "factor", "base", "mensual"), EJEMPLOS)
async def test_ejemplos_de_la_historia(edad, saldo, plazo, factor, base, mensual):
    perfilador = _PerfilOk(factor) if factor else _PerfilInexistente()

    cot = await _servicio(perfilador).crear_cotizacion(
        solicitud(edad=edad, saldo=saldo, plazo=plazo)
    )

    assert cot.oferta.prima_base_mensual == Decimal(base)
    assert cot.oferta.prima_mensual == Decimal(mensual)
    assert cot.oferta.personalizado is (factor is not None)


async def test_60_anos_con_240_meses_termina_a_los_80_y_se_rechaza():
    with pytest.raises(SolicitudInvalida) as error:
        await _servicio().crear_cotizacion(solicitud(edad=60, saldo="150000000", plazo=240))

    assert error.value.errores[0]["campo"] == "datosCredito.plazoRestanteMeses"
    assert "180 meses" in error.value.errores[0]["mensaje"]  # 75 años - 60 años


@pytest.mark.parametrize("edad", [17, 66, 0, 120])
async def test_edad_fuera_de_18_a_65_se_rechaza_con_el_campo_y_el_rango(edad):
    with pytest.raises(SolicitudInvalida) as error:
        await _servicio().crear_cotizacion(solicitud(edad=edad, plazo=12))

    assert error.value.errores == [{"campo": "edad", "mensaje": "Debe estar entre 18 y 65 años"}]


@pytest.mark.parametrize("edad", [18, 65])
def test_los_limites_de_edad_son_validos(edad):
    validar_solicitud(solicitud(edad=edad, plazo=12))


def test_el_plazo_que_termina_justo_a_los_75_es_valido_y_un_mes_mas_no():
    validar_solicitud(solicitud(edad=40, plazo=420))  # 40 + 35 años = 75
    with pytest.raises(SolicitudInvalida):
        validar_solicitud(solicitud(edad=40, plazo=421))


# --- cálculo ---


def test_prima_base_es_saldo_por_tasa_sobre_mil_redondeada_al_peso():
    assert calcular_prima_base(datos_credito(saldo="98000000"), Decimal("0.137")) == Decimal(
        "13426"
    )
    # 100.000.001 × 0,5 ÷ 1.000 = 50.000,0005 → 50.000
    assert calcular_prima_base(datos_credito(saldo="100000001"), Decimal("0.5")) == Decimal("50000")
    # mitad hacia arriba: 1.234,5 → 1.235
    assert calcular_prima_base(datos_credito(saldo="2469000"), Decimal("0.5")) == Decimal("1235")


async def test_la_cotizacion_guarda_los_insumos_del_calculo():
    cot = await _servicio().crear_cotizacion(solicitud(edad=37, saldo="178500000", plazo=165))

    assert cot.edad == 37
    assert cot.tasa == Decimal("0.196")
    assert cot.version_tarifa == TARIFA_SEMILLA.version
    assert cot.origen_datos == "DECLARADO"
    assert cot.datos_credito.saldo_insoluto == Decimal("178500000")
    assert cot.perfil_riesgo.factor_ajuste == Decimal("0.90")
    assert cot.oferta.suma_asegurada == Decimal("178500000")
    assert cot.oferta.cobertura_meses == 165


async def test_crear_cotizacion_personalizada_lleva_los_factores():
    cot = await _servicio().crear_cotizacion(solicitud())

    assert cot.oferta.personalizado is True
    assert cot.perfil_riesgo is not None
    assert cot.perfil_riesgo.factores[0].descripcion == "Historial de pagos excelente"


async def test_crear_cotizacion_cae_a_tarifa_estandar_si_perfilamiento_falla():
    cot = await _servicio(_PerfilCaido()).crear_cotizacion(solicitud())

    assert cot.oferta.personalizado is False
    assert cot.perfil_riesgo is None
    assert cot.oferta.prima_mensual == cot.oferta.prima_base_mensual
    assert cot.oferta.fuentes_no_disponibles == ("perfilamiento",)


async def test_crear_cotizacion_cae_a_tarifa_estandar_si_el_perfil_no_existe_todavia():
    cot = await _servicio(_PerfilInexistente()).crear_cotizacion(solicitud())

    assert cot.oferta.personalizado is False
    assert cot.perfil_riesgo is None


async def test_sin_tarifa_no_hay_cotizacion():
    with pytest.raises(DependenciaNoDisponible):
        await _servicio(tarifa=FakeTarifa(disponible=False)).crear_cotizacion(solicitud())


# --- una sola cotización activa por cliente ---


async def test_la_cotizacion_creada_queda_como_la_activa():
    servicio = _servicio()

    creada = await servicio.crear_cotizacion(solicitud())

    assert await servicio.obtener_cotizacion_activa("cli-1") == creada


async def test_una_cotizacion_nueva_reemplaza_a_la_anterior():
    servicio = _servicio()
    await servicio.crear_cotizacion(solicitud(saldo="100000000"))

    nueva = await servicio.crear_cotizacion(solicitud(saldo="200000000"))

    activa = await servicio.obtener_cotizacion_activa("cli-1")
    assert activa == nueva
    assert activa.datos_credito.saldo_insoluto == Decimal("200000000")


async def test_cada_cliente_tiene_su_propia_cotizacion_activa():
    servicio = _servicio()
    await servicio.crear_cotizacion(solicitud(cliente_id="cli-1", saldo="100000000"))
    await servicio.crear_cotizacion(solicitud(cliente_id="cli-2", saldo="200000000"))

    primera = await servicio.obtener_cotizacion_activa("cli-1")

    assert primera.datos_credito.saldo_insoluto == Decimal("100000000")


async def test_sin_cotizacion_activa_no_se_encuentra():
    with pytest.raises(RecursoNoEncontrado):
        await _servicio().obtener_cotizacion_activa("cli-sin-cotizacion")


# --- cobertura opcional de Hogar ---
# (valor del crédito, suma asegurada, prima neta, IVA, total)
EJEMPLOS_HOGAR = [
    ("150000000", "150000000", "14850", "2822", "17672"),  # IVA 2.821,5 sube con ROUND_HALF_UP
    ("220000000", "220000000", "21780", "4138", "25918"),
    ("320000000", "240000000", "23760", "4514", "28274"),  # se pasa del tope
    ("240000000", "240000000", "23760", "4514", "28274"),  # justo en el tope
]


@pytest.mark.parametrize(("valor", "suma", "neta", "iva", "total"), EJEMPLOS_HOGAR)
def test_hogar_suma_asegurada_con_tope_e_iva(valor, suma, neta, iva, total):
    hogar = calcular_cobertura_hogar(datos_credito(valor=valor), TARIFA_SEMILLA.hogar)

    assert hogar.codigo == CodigoCobertura.HOGAR
    assert hogar.obligatoria is False
    assert hogar.suma_asegurada == Decimal(suma)
    assert hogar.prima_neta == Decimal(neta)
    assert hogar.iva == Decimal(iva)
    assert hogar.prima_total == Decimal(total)


async def test_el_desglose_trae_vida_sin_iva_y_hogar():
    cot = await _servicio().crear_cotizacion(solicitud())

    vida, hogar = calcular_desglose(cot.oferta, cot.hogar)

    assert vida.codigo == CodigoCobertura.VIDA
    assert vida.obligatoria is True
    assert vida.suma_asegurada == cot.oferta.suma_asegurada
    assert vida.prima_neta == cot.oferta.prima_mensual
    assert vida.iva == 0
    assert vida.prima_total == cot.oferta.prima_mensual
    assert hogar.codigo == CodigoCobertura.HOGAR


async def test_el_factor_del_perfil_no_afecta_a_hogar():
    con_descuento = await _servicio(_PerfilOk("0.85")).crear_cotizacion(solicitud())
    con_recargo = await _servicio(_PerfilOk("1.65")).crear_cotizacion(solicitud())

    assert con_descuento.hogar == con_recargo.hogar


async def test_sin_perfil_el_desglose_usa_la_prima_estandar_de_vida():
    cot = await _servicio(_PerfilInexistente()).crear_cotizacion(solicitud())

    vida, _ = calcular_desglose(cot.oferta, cot.hogar)

    assert vida.prima_neta == cot.oferta.prima_base_mensual


async def test_la_cotizacion_calcula_hogar_con_la_tarifa_que_trae_productos():
    tarifa = replace(
        TARIFA_SEMILLA,
        hogar=TarifaHogar(Decimal("0.2"), Decimal("100000000"), Decimal("0.16")),
    )

    cot = await _servicio(tarifa=FakeTarifa(tarifa=tarifa)).crear_cotizacion(solicitud())

    # Crédito de $150M, tope de $100M: 100.000.000 × 0,2 ÷ 1.000 = 20.000; impuesto 16 % = 3.200.
    assert cot.hogar.suma_asegurada == Decimal("100000000")
    assert cot.hogar.prima_neta == Decimal("20000")
    assert cot.hogar.iva == Decimal("3200")


async def test_una_sola_lectura_de_la_tarifa_sirve_para_vida_y_hogar():
    tarifa = FakeTarifa()

    await _servicio(tarifa=tarifa).crear_cotizacion(solicitud())

    assert tarifa.llamadas == 1


async def test_una_cotizacion_anterior_a_hogar_se_completa_al_consultarla():
    repositorio = FakeCotizacionRepository()
    await repositorio.reemplazar(cotizacion(sin_hogar=True))

    cot = await _servicio(repositorio=repositorio).obtener_cotizacion_activa("cli-1")

    assert cot.hogar.prima_total == Decimal("17672")  # crédito de $150M de la factoría
