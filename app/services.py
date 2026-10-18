"""Orquestación y rating del servicio de Cotización."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.domain import (
    EDAD_MAXIMA,
    EDAD_MAXIMA_AL_TERMINAR,
    EDAD_MINIMA,
    CoberturaPrecio,
    CodigoCobertura,
    Cotizacion,
    DatosCredito,
    DependenciaNoDisponible,
    Moneda,
    Oferta,
    OrigenDatos,
    PerfilRiesgo,
    SolicitudCotizacion,
    SolicitudInvalida,
    Vigencia,
)
from app.logging_utils import sanear_para_log
from app.ports import CotizacionRepositoryPort, PerfilRiesgoPort, TarifaPort

logger = logging.getLogger("cotizacion.services")
VIGENCIA_COTIZACION = timedelta(days=30)

_PESO = Decimal("1")
_MIL = Decimal("1000")

# Cobertura opcional de Hogar: tarifa fija (Licitación 002-2025 de Banco Serfinanza).
HOGAR_SUMA_ASEGURADA_TOPE = Decimal("240000000")
HOGAR_TASA_MENSUAL_POR_MIL = Decimal("0.099")
IVA = Decimal("0.19")  # solo Hogar; el seguro de vida está excluido (Estatuto Tributario, art. 427)


def validar_solicitud(solicitud: SolicitudCotizacion) -> None:
    """Edad entre 18 y 65 y que el crédito termine a los 75 años o antes (BITS-95).

    ``edad + plazo_restante_meses / 12 <= 75`` se calcula en meses para no redondear.
    """
    edad = solicitud.edad
    if not EDAD_MINIMA <= edad <= EDAD_MAXIMA:
        raise SolicitudInvalida(
            "La edad está fuera del rango permitido",
            errores=[
                {
                    "campo": "edad",
                    "mensaje": f"Debe estar entre {EDAD_MINIMA} y {EDAD_MAXIMA} años",
                }
            ],
        )
    plazo_maximo = EDAD_MAXIMA_AL_TERMINAR * 12 - edad * 12
    if solicitud.datos_credito.plazo_restante_meses > plazo_maximo:
        raise SolicitudInvalida(
            "El crédito termina después de la edad máxima permitida",
            errores=[
                {
                    "campo": "datosCredito.plazoRestanteMeses",
                    "mensaje": (
                        f"Con {edad} años el plazo restante puede ser de hasta {plazo_maximo} "
                        f"meses: el crédito debe terminar a los {EDAD_MAXIMA_AL_TERMINAR} años o "
                        "antes"
                    ),
                }
            ],
        )


def _a_pesos(valor: Decimal) -> Decimal:
    return valor.quantize(_PESO, rounding=ROUND_HALF_UP)


def calcular_prima_base(datos: DatosCredito, tasa_mensual_por_mil: Decimal) -> Decimal:
    """Prima mensual con tarifa estándar (sin ajuste por perfil), redondeada al peso:
    ``saldo_insoluto × tasa ÷ 1.000``."""
    return _a_pesos(datos.saldo_insoluto * tasa_mensual_por_mil / _MIL)


def calcular_cobertura_hogar(datos: DatosCredito) -> CoberturaPrecio:
    """Cobertura opcional de Hogar (incendio y terremoto). Tarifa fija, sin ajuste por perfil.

    ``suma_asegurada = min(tope, valor_credito)``; ``prima_neta = suma_asegurada × tasa ÷ 1.000``;
    ``iva = prima_neta × 19 %``. Cada monto se redondea al peso por separado.
    """
    suma_asegurada = min(HOGAR_SUMA_ASEGURADA_TOPE, datos.valor_credito)
    prima_neta = _a_pesos(suma_asegurada * HOGAR_TASA_MENSUAL_POR_MIL / _MIL)
    return CoberturaPrecio(
        codigo=CodigoCobertura.HOGAR,
        obligatoria=False,
        suma_asegurada=suma_asegurada,
        prima_neta=prima_neta,
        iva=_a_pesos(prima_neta * IVA),
    )


def calcular_desglose(datos: DatosCredito, oferta: Oferta) -> tuple[CoberturaPrecio, ...]:
    """Precio de cada cobertura: Vida (obligatoria, sin IVA, con la prima de la oferta) y Hogar.

    Se deriva de lo que la cotización ya guarda, por eso no se persiste.
    """
    vida = CoberturaPrecio(
        codigo=CodigoCobertura.VIDA,
        obligatoria=True,
        suma_asegurada=oferta.suma_asegurada,
        prima_neta=oferta.prima_mensual,
        iva=Decimal(0),
    )
    return (vida, calcular_cobertura_hogar(datos))


class CotizacionService:
    def __init__(
        self,
        perfilador: PerfilRiesgoPort,
        tarifa: TarifaPort,
        repositorio: CotizacionRepositoryPort,
    ) -> None:
        self._perfilador = perfilador
        self._tarifa = tarifa
        self._repositorio = repositorio

    async def crear_cotizacion(self, solicitud: SolicitudCotizacion) -> Cotizacion:
        """Calcula la cotización y la deja como la activa del cliente (reemplaza la anterior)."""
        validar_solicitud(solicitud)
        datos = solicitud.datos_credito

        logger.info(
            "crear_cotizacion: solicitud recibida cliente_id=%s",
            sanear_para_log(solicitud.cliente_id),
        )

        inicio = time.perf_counter()
        # Las dos lecturas son independientes (caché de perfil y de tarifa): en paralelo.
        perfil, tarifa = await asyncio.gather(
            self._perfil_o_ninguno(solicitud.cliente_id), self._tarifa.obtener()
        )
        duracion_ms = round((time.perf_counter() - inicio) * 1000, 1)
        logger.info(
            "crear_cotizacion: perfil y tarifa resueltos en %s ms perfil_disponible=%s "
            "version_tarifa=%s",
            duracion_ms,
            perfil is not None,
            tarifa.version,
        )

        tasa = tarifa.tasa_para(solicitud.edad)
        prima_base = calcular_prima_base(datos, tasa)
        oferta = self._armar_oferta(datos, prima_base, perfil)

        ahora = datetime.now(UTC)
        cotizacion = Cotizacion(
            cliente_id=solicitud.cliente_id,
            edad=solicitud.edad,
            datos_credito=datos,
            origen_datos=OrigenDatos.DECLARADO,
            tasa=tasa,
            version_tarifa=tarifa.version,
            oferta=oferta,
            perfil_riesgo=perfil,
            vigencia=Vigencia(ahora, ahora + VIGENCIA_COTIZACION),
            creada_en=ahora,
        )
        await self._repositorio.reemplazar(cotizacion)
        logger.info(
            "crear_cotizacion: cotizacion activa guardada cliente_id=%s personalizado=%s",
            sanear_para_log(solicitud.cliente_id),
            oferta.personalizado,
        )
        return cotizacion

    async def obtener_cotizacion_activa(self, cliente_id: str) -> Cotizacion:
        logger.info(
            "obtener_cotizacion_activa: consultando cliente_id=%s", sanear_para_log(cliente_id)
        )
        return await self._repositorio.obtener_activa(cliente_id)

    async def _perfil_o_ninguno(self, cliente_id: str) -> PerfilRiesgo | None:
        try:
            return await self._perfilador.obtener_perfil(cliente_id)
        except DependenciaNoDisponible:
            logger.warning("crear_cotizacion: perfilamiento no disponible, cae a tarifa estandar")
            return None

    @staticmethod
    def _armar_oferta(
        datos: DatosCredito, prima_base: Decimal, perfil: PerfilRiesgo | None
    ) -> Oferta:
        if perfil is None:
            return Oferta(
                prima_mensual=prima_base,
                prima_base_mensual=prima_base,
                suma_asegurada=datos.saldo_insoluto,
                cobertura_meses=datos.plazo_restante_meses,
                moneda=Moneda.COP,
                personalizado=False,
                fuentes_no_disponibles=("perfilamiento",),
            )
        return Oferta(
            prima_mensual=_a_pesos(prima_base * perfil.factor_ajuste),
            prima_base_mensual=prima_base,
            suma_asegurada=datos.saldo_insoluto,
            cobertura_meses=datos.plazo_restante_meses,
            moneda=Moneda.COP,
            personalizado=True,
            fuentes_no_disponibles=perfil.fuentes_no_disponibles,
        )
