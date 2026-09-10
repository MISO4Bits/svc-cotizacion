from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.schemas import (
    CotizacionOut,
    FactorRiesgoOut,
    OfertaOut,
    PerfilRiesgoOut,
    SolicitudCotizacionIn,
    VigenciaOut,
)
from app.domain import (
    ActividadFisica,
    Cotizacion,
    CuestionarioHabitos,
    DatosCredito,
    SolicitudCotizacion,
)
from app.services import CotizacionService

router = APIRouter(tags=["Cotización"])

ClienteId = Annotated[str, Header(alias="X-Cliente-Id", min_length=1, max_length=64)]


def get_service(request: Request) -> CotizacionService:
    return request.app.state.service


ServiceDep = Annotated[CotizacionService, Depends(get_service)]


def _a_dominio(cliente_id: str, payload: SolicitudCotizacionIn) -> SolicitudCotizacion:
    dc = payload.datos_credito
    q = payload.cuestionario_habitos
    return SolicitudCotizacion(
        cliente_id=cliente_id,
        datos_credito=DatosCredito(
            valor_credito=dc.valor_credito,
            plazo_meses=dc.plazo_meses,
            edad=dc.edad,
            entidad_acreedora=dc.entidad_acreedora,
            saldo_insoluto=dc.saldo_insoluto,
        ),
        cuestionario_habitos=CuestionarioHabitos(
            consume_tabaco=q.consume_tabaco,
            actividad_fisica=ActividadFisica(q.actividad_fisica),
            condiciones_preexistentes=q.condiciones_preexistentes,
            dependientes_economicos=q.dependientes_economicos,
        ),
    )


def _a_salida(cot: Cotizacion) -> CotizacionOut:
    o = cot.oferta
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
        id=cot.id,
        estado=str(cot.estado),
        producto=cot.producto,
        oferta=OfertaOut(
            prima_mensual=float(o.prima_mensual),
            prima_base_mensual=float(o.prima_base_mensual),
            suma_asegurada=float(o.suma_asegurada),
            cobertura_meses=o.cobertura_meses,
            moneda=str(o.moneda),
            personalizado=o.personalizado,
            fuentes_no_disponibles=list(o.fuentes_no_disponibles),
        ),
        perfil_riesgo=perfil,
        vigencia_cotizacion=VigenciaOut(desde=cot.vigencia.desde, hasta=cot.vigencia.hasta),
        creada_en=cot.creada_en,
    )


@router.post(
    "/cotizaciones",
    response_model=CotizacionOut,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def crear_cotizacion(
    payload: SolicitudCotizacionIn,
    cliente_id: ClienteId,
    service: ServiceDep,
) -> CotizacionOut:
    cotizacion = await service.crear_cotizacion(_a_dominio(cliente_id, payload))
    return _a_salida(cotizacion)


@router.get(
    "/cotizaciones/{cotizacion_id}",
    response_model=CotizacionOut,
    response_model_exclude_none=True,
)
async def obtener_cotizacion(
    cotizacion_id: str,
    cliente_id: ClienteId,
    service: ServiceDep,
) -> CotizacionOut:
    cotizacion = await service.obtener_cotizacion(cotizacion_id, cliente_id)
    return _a_salida(cotizacion)
