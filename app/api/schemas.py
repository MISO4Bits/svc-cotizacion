"""Modelos Pydantic de la API. Reflejan ``openapi/openapi.yaml``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

RamoLiteral = Literal["PROTECCION_DISPOSITIVO"]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


# --- entrada ---


class CanalIn(_Model):
    tipo: Literal["SOCIO", "ASESOR"]
    socio_id: str = Field(min_length=1, max_length=40)


class DispositivoIn(_Model):
    tipo: Literal["CELULAR", "PORTATIL", "TABLET"]
    valor_asegurado: Decimal = Field(gt=0, le=50_000_000)
    antiguedad_meses: int = Field(ge=0, le=120)


class SolicitanteIn(_Model):
    edad: int = Field(ge=18, le=99)
    pais: Literal["CO"]


class SolicitudCotizacionIn(_Model):
    ramo: RamoLiteral
    canal: CanalIn
    dispositivo: DispositivoIn
    solicitante: SolicitanteIn


# --- salida ---


class PrimaOut(_Model):
    prima_pura: float
    gastos: float
    impuestos: float
    total: float
    moneda: Literal["COP"]


class CoberturaOut(_Model):
    codigo: str
    nombre: str
    suma_asegurada: float
    deducible: float


class VigenciaOut(_Model):
    desde: datetime
    hasta: datetime


class CotizacionOut(_Model):
    id: str
    estado: Literal["VIGENTE", "EXPIRADA", "ACEPTADA", "RECHAZADA"]
    ramo: RamoLiteral
    prima: PrimaOut
    coberturas: list[CoberturaOut]
    vigencia_cotizacion: VigenciaOut
    creada_en: datetime
