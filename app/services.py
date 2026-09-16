"""Orquestación y rating del servicio de Cotización."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domain import (
    Cotizacion,
    DatosCredito,
    DependenciaNoDisponible,
    EstadoCotizacion,
    Moneda,
    Oferta,
    PerfilRiesgo,
    SolicitudCotizacion,
    Vigencia,
)
from app.logging_utils import sanear_para_log
from app.ports import CotizacionRepositoryPort, PerfilRiesgoPort

logger = logging.getLogger("cotizacion.services")
VIGENCIA_COTIZACION = timedelta(days=30)

_PESO = Decimal("1")
# TODO: la tarifa base vendrá de ReglasRatingPort (Productos y Configuración) — ver diseño de David.
_TASA_MENSUAL_BASE = Decimal("0.00035")  # proporción de la suma asegurada, por mes


def _factor_edad(edad: int) -> Decimal:
    if edad <= 35:
        return Decimal("1.00")
    if edad <= 50:
        return Decimal("1.40")
    return Decimal("1.90")


def calcular_prima_base(datos: DatosCredito) -> Decimal:
    """Prima mensual con tarifa estándar (sin ajuste por perfil).

    suma_asegurada = saldo insoluto (protección de la deuda).
    """
    ajustada = datos.saldo_insoluto * _TASA_MENSUAL_BASE * _factor_edad(datos.edad)
    return ajustada.quantize(_PESO)


class CotizacionService:
    def __init__(
        self,
        perfilador: PerfilRiesgoPort,
        repositorio: CotizacionRepositoryPort,
    ) -> None:
        self._perfilador = perfilador
        self._repositorio = repositorio

    async def crear_cotizacion(self, solicitud: SolicitudCotizacion) -> Cotizacion:
        datos = solicitud.datos_credito
        prima_base = calcular_prima_base(datos)

        logger.info(
            "crear_cotizacion: solicitud recibida cliente_id=%s",
            sanear_para_log(solicitud.cliente_id),
        )

        inicio = time.perf_counter()
        try:
            perfil = await self._perfilador.perfilar(solicitud)
        except DependenciaNoDisponible:
            logger.warning("crear_cotizacion: perfilamiento no disponible, cae a tarifa estandar")
            perfil = None
        duracion_ms = round((time.perf_counter() - inicio) * 1000, 1)
        logger.info(
            "crear_cotizacion: perfilamiento resuelto en %s ms disponible=%s",
            duracion_ms,
            perfil is not None,
        )

        oferta = self._armar_oferta(datos, prima_base, perfil)

        ahora = datetime.now(UTC)
        cotizacion = Cotizacion(
            id=str(uuid4()),
            cliente_id=solicitud.cliente_id,
            estado=EstadoCotizacion.VIGENTE,
            oferta=oferta,
            perfil_riesgo=perfil,
            vigencia=Vigencia(ahora, ahora + VIGENCIA_COTIZACION),
            creada_en=ahora,
        )
        await self._repositorio.guardar(cotizacion)
        logger.info(
            "crear_cotizacion: cotizacion creada id=%s personalizado=%s",
            cotizacion.id,
            oferta.personalizado,
        )
        return cotizacion

    async def obtener_cotizacion(self, cotizacion_id: str, cliente_id: str) -> Cotizacion:
        logger.info(
            "obtener_cotizacion: consultando id=%s cliente_id=%s",
            sanear_para_log(cotizacion_id),
            sanear_para_log(cliente_id),
        )
        return await self._repositorio.obtener(cotizacion_id, cliente_id)

    @staticmethod
    def _armar_oferta(
        datos: DatosCredito, prima_base: Decimal, perfil: PerfilRiesgo | None
    ) -> Oferta:
        if perfil is None:
            return Oferta(
                prima_mensual=prima_base,
                prima_base_mensual=prima_base,
                suma_asegurada=datos.saldo_insoluto,
                cobertura_meses=datos.plazo_meses,
                moneda=Moneda.COP,
                personalizado=False,
                fuentes_no_disponibles=("perfilamiento",),
            )
        prima = (prima_base * perfil.factor_ajuste).quantize(_PESO)
        return Oferta(
            prima_mensual=prima,
            prima_base_mensual=prima_base,
            suma_asegurada=datos.saldo_insoluto,
            cobertura_meses=datos.plazo_meses,
            moneda=Moneda.COP,
            personalizado=True,
            fuentes_no_disponibles=perfil.fuentes_no_disponibles,
        )
