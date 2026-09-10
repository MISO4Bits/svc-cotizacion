from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.schemas import (
    CoberturaOut,
    CotizacionOut,
    PrimaOut,
    SolicitudCotizacionIn,
    VigenciaOut,
)
from app.domain import (
    Canal,
    Cotizacion,
    Dispositivo,
    Ramo,
    Solicitante,
    SolicitudCotizacion,
    TipoCanal,
    TipoDispositivo,
)
from app.services import CotizacionService

router = APIRouter(prefix="/v1")


def get_service(request: Request) -> CotizacionService:
    return request.app.state.service


ServiceDep = Annotated[CotizacionService, Depends(get_service)]


def _a_dominio(payload: SolicitudCotizacionIn) -> SolicitudCotizacion:
    return SolicitudCotizacion(
        ramo=Ramo(payload.ramo),
        canal=Canal(TipoCanal(payload.canal.tipo), payload.canal.socio_id),
        dispositivo=Dispositivo(
            TipoDispositivo(payload.dispositivo.tipo),
            payload.dispositivo.valor_asegurado,
            payload.dispositivo.antiguedad_meses,
        ),
        solicitante=Solicitante(payload.solicitante.edad, payload.solicitante.pais),
    )


def _a_salida(cot: Cotizacion) -> CotizacionOut:
    return CotizacionOut(
        id=cot.id,
        estado=str(cot.estado),
        ramo=str(cot.ramo),
        prima=PrimaOut(
            prima_pura=float(cot.prima.prima_pura),
            gastos=float(cot.prima.gastos),
            impuestos=float(cot.prima.impuestos),
            total=float(cot.prima.total),
            moneda=str(cot.prima.moneda),
        ),
        coberturas=[
            CoberturaOut(
                codigo=c.codigo,
                nombre=c.nombre,
                suma_asegurada=float(c.suma_asegurada),
                deducible=float(c.deducible),
            )
            for c in cot.coberturas
        ],
        vigencia_cotizacion=VigenciaOut(desde=cot.vigencia.desde, hasta=cot.vigencia.hasta),
        creada_en=cot.creada_en,
    )


@router.post(
    "/cotizaciones",
    response_model=CotizacionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Cotización"],
)
async def crear_cotizacion(payload: SolicitudCotizacionIn, service: ServiceDep) -> CotizacionOut:
    cotizacion = await service.crear_cotizacion(_a_dominio(payload))
    return _a_salida(cotizacion)
