"""Modelos Pydantic de la API. Reflejan ``openapi/openapi.yaml``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


# --- entrada ---


class DatosCreditoIn(_Model):
    valor_credito: Decimal = Field(ge=10_000_000)
    plazo_meses: int = Field(ge=12, le=480)
    edad: int = Field(ge=18, le=65)
    entidad_acreedora: str = Field(min_length=2, max_length=80)
    saldo_insoluto: Decimal = Field(gt=0)


class CuestionarioHabitosIn(_Model):
    consume_tabaco: bool
    actividad_fisica: Literal["NUNCA", "OCASIONAL", "REGULAR"]
    condiciones_preexistentes: bool
    dependientes_economicos: int = Field(ge=0, le=20)


class SolicitudCotizacionIn(_Model):
    datos_credito: DatosCreditoIn
    cuestionario_habitos: CuestionarioHabitosIn


# --- salida ---


class FactorRiesgoOut(_Model):
    descripcion: str
    efecto: Literal["POSITIVO", "NEGATIVO"]
    peso_relativo: float | None = None


class PerfilRiesgoOut(_Model):
    nivel_riesgo: Literal["BAJO", "MEDIO", "ALTO"]
    factores: list[FactorRiesgoOut]


class OfertaOut(_Model):
    prima_mensual: float
    prima_base_mensual: float
    suma_asegurada: float
    cobertura_meses: int
    moneda: Literal["COP"]
    personalizado: bool
    fuentes_no_disponibles: list[str] = Field(default_factory=list)


class VigenciaOut(_Model):
    desde: datetime
    hasta: datetime


class CotizacionOut(_Model):
    id: str
    estado: Literal["VIGENTE", "EXPIRADA"]
    producto: Literal["VIDA_HIPOTECARIO"]
    oferta: OfertaOut
    perfil_riesgo: PerfilRiesgoOut | None = None
    vigencia_cotizacion: VigenciaOut
    creada_en: datetime
