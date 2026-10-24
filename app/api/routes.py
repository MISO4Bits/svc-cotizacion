from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, status

from app.api.schemas import (
    CoberturaPrecioOut,
    CotizacionActivaInternaOut,
    CotizacionOut,
    DatosCreditoOut,
    DesgloseOut,
    FactorRiesgoOut,
    OfertaOut,
    PerfilRiesgoOut,
    SolicitudCotizacionIn,
    VigenciaOut,
)
from app.domain import Cotizacion, DatosCredito, SolicitudCotizacion
from app.logging_utils import sanear_para_log
from app.services import CotizacionService, calcular_desglose

router = APIRouter(tags=["Cotización"])

logger = logging.getLogger("cotizacion.api")

ClienteId = Annotated[str, Header(alias="X-Cliente-Id", min_length=1, max_length=64)]


def get_service(request: Request) -> CotizacionService:
    return request.app.state.service


ServiceDep = Annotated[CotizacionService, Depends(get_service)]


def _a_dominio(cliente_id: str, payload: SolicitudCotizacionIn) -> SolicitudCotizacion:
    dc = payload.datos_credito
    return SolicitudCotizacion(
        cliente_id=cliente_id,
        edad=payload.edad,
        datos_credito=DatosCredito(
            valor_credito=dc.valor_credito,
            plazo_restante_meses=dc.plazo_restante_meses,
            entidad_acreedora=dc.entidad_acreedora,
            saldo_insoluto=dc.saldo_insoluto,
        ),
    )


def _a_salida(cot: Cotizacion) -> CotizacionOut:
    o = cot.oferta
    d = cot.datos_credito
    perfil = None
    if cot.perfil_riesgo is not None:
        perfil = PerfilRiesgoOut(
            nivel_riesgo=str(cot.perfil_riesgo.nivel_riesgo),
            factores=[
                FactorRiesgoOut(
                    descripcion=f.descripcion,
                    efecto=str(f.efecto),
                    peso_relativo=(float(f.peso_relativo) if f.peso_relativo is not None else None),
                )
                for f in cot.perfil_riesgo.factores
            ],
        )
    return CotizacionOut(
        estado=str(cot.estado_en(datetime.now(UTC))),
        producto=cot.producto,
        datos_credito=DatosCreditoOut(
            valor_credito=float(d.valor_credito),
            plazo_restante_meses=d.plazo_restante_meses,
            entidad_acreedora=d.entidad_acreedora,
            saldo_insoluto=float(d.saldo_insoluto),
        ),
        origen_datos=str(cot.origen_datos),
        oferta=OfertaOut(
            prima_mensual=float(o.prima_mensual),
            prima_base_mensual=float(o.prima_base_mensual),
            suma_asegurada=float(o.suma_asegurada),
            cobertura_meses=o.cobertura_meses,
            moneda=str(o.moneda),
            personalizado=o.personalizado,
            fuentes_no_disponibles=list(o.fuentes_no_disponibles),
            desglose=DesgloseOut(
                coberturas=[
                    CoberturaPrecioOut(
                        codigo=str(c.codigo),
                        obligatoria=c.obligatoria,
                        suma_asegurada=float(c.suma_asegurada),
                        prima_neta=float(c.prima_neta),
                        iva=float(c.iva),
                        prima_total=float(c.prima_total),
                    )
                    for c in calcular_desglose(o, cot.hogar)
                ]
            ),
        ),
        perfil_riesgo=perfil,
        vigencia_cotizacion=VigenciaOut(desde=cot.vigencia.desde, hasta=cot.vigencia.hasta),
        creada_en=cot.creada_en,
    )


@router.post(
    "/v1/cotizaciones",
    response_model=CotizacionOut,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def crear_cotizacion(
    payload: SolicitudCotizacionIn,
    cliente_id: ClienteId,
    service: ServiceDep,
) -> CotizacionOut:
    logger.info(
        "POST /v1/cotizaciones: solicitud recibida cliente_id=%s", sanear_para_log(cliente_id)
    )
    cotizacion = await service.crear_cotizacion(_a_dominio(cliente_id, payload))
    return _a_salida(cotizacion)


@router.get(
    "/v1/cotizaciones/actual",
    response_model=CotizacionOut,
    response_model_exclude_none=True,
)
async def obtener_cotizacion_activa(
    cliente_id: ClienteId,
    service: ServiceDep,
) -> CotizacionOut:
    logger.info(
        "GET /v1/cotizaciones/actual: solicitud recibida cliente_id=%s",
        sanear_para_log(cliente_id),
    )
    cotizacion = await service.obtener_cotizacion_activa(cliente_id)
    return _a_salida(cotizacion)


@router.delete("/v1/cotizaciones/actual", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_cotizacion_activa(
    cliente_id: ClienteId,
    service: ServiceDep,
) -> None:
    logger.info(
        "DELETE /v1/cotizaciones/actual: solicitud recibida cliente_id=%s",
        sanear_para_log(cliente_id),
    )
    await service.eliminar_cotizacion_activa(cliente_id)


@router.get(
    "/v1/clientes/{cliente_id}/cotizacion-activa",
    response_model=CotizacionActivaInternaOut,
    tags=["Cotización (interno)"],
)
async def obtener_cotizacion_activa_interna(
    cliente_id: Annotated[str, Path(min_length=1, max_length=64)],
    service: ServiceDep,
) -> CotizacionActivaInternaOut:
    """Para CoreTransaccional: la cotización activa por ``clienteId``, aunque esté expirada."""
    logger.info(
        "GET /v1/clientes/%s/cotizacion-activa: solicitud recibida", sanear_para_log(cliente_id)
    )
    cot = await service.obtener_cotizacion_activa(cliente_id)
    d = cot.datos_credito
    return CotizacionActivaInternaOut(
        estado=str(cot.estado_en(datetime.now(UTC))),
        edad=cot.edad,
        datos_credito=DatosCreditoOut(
            valor_credito=float(d.valor_credito),
            plazo_restante_meses=d.plazo_restante_meses,
            entidad_acreedora=d.entidad_acreedora,
            saldo_insoluto=float(d.saldo_insoluto),
        ),
        origen_datos=str(cot.origen_datos),
        tasa=float(cot.tasa),
        version_tarifa=cot.version_tarifa,
        cobertura_meses=cot.oferta.cobertura_meses,
        coberturas=[
            CoberturaPrecioOut(
                codigo=str(c.codigo),
                obligatoria=c.obligatoria,
                suma_asegurada=float(c.suma_asegurada),
                prima_neta=float(c.prima_neta),
                iva=float(c.iva),
                prima_total=float(c.prima_total),
            )
            for c in calcular_desglose(cot.oferta, cot.hogar)
        ],
        vigencia_cotizacion=VigenciaOut(desde=cot.vigencia.desde, hasta=cot.vigencia.hasta),
        creada_en=cot.creada_en,
    )
