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
    plazo_restante_meses: int = Field(ge=1, le=480)
    entidad_acreedora: str = Field(min_length=2, max_length=80)
    saldo_insoluto: Decimal = Field(gt=0)


class SolicitudCotizacionIn(_Model):
    # Ya calculada por el BFF a partir de la fecha de nacimiento del registro. El rango
    # permitido (18 a 65) lo valida el servicio, para responder con el campo y el rango.
    edad: int
    datos_credito: DatosCreditoIn


# --- salida ---


class DatosCreditoOut(_Model):
    valor_credito: float
    plazo_restante_meses: int
    entidad_acreedora: str
    saldo_insoluto: float


class FactorRiesgoOut(_Model):
    descripcion: str
    efecto: Literal["POSITIVO", "NEGATIVO"]
    peso_relativo: float | None = None


class PerfilRiesgoOut(_Model):
    nivel_riesgo: Literal["BAJO", "MEDIO", "ALTO"]
    factores: list[FactorRiesgoOut]


class CoberturaPrecioOut(_Model):
    codigo: Literal["VIDA", "HOGAR"]
    obligatoria: bool
    suma_asegurada: float
    prima_neta: float
    iva: float
    prima_total: float


class DesgloseOut(_Model):
    coberturas: list[CoberturaPrecioOut]


class OfertaOut(_Model):
    prima_mensual: float
    prima_base_mensual: float
    suma_asegurada: float
    cobertura_meses: int
    moneda: Literal["COP"]
    personalizado: bool
    fuentes_no_disponibles: list[str] = Field(default_factory=list)
    desglose: DesgloseOut


class VigenciaOut(_Model):
    desde: datetime
    hasta: datetime


class CotizacionOut(_Model):
    estado: Literal["VIGENTE", "EXPIRADA"]
    producto: Literal["VIDA_HIPOTECARIO"]
    datos_credito: DatosCreditoOut
    origen_datos: Literal["CONFIRMADO", "DECLARADO"]
    oferta: OfertaOut
    perfil_riesgo: PerfilRiesgoOut | None = None
    vigencia_cotizacion: VigenciaOut
    creada_en: datetime


class CotizacionActivaInternaOut(_Model):
    """Lo que CoreTransaccional guarda en la póliza (ruta interna, no pasa por el gateway)."""

    estado: Literal["VIGENTE", "EXPIRADA"]
    edad: int
    datos_credito: DatosCreditoOut
    origen_datos: Literal["CONFIRMADO", "DECLARADO"]
    tasa: float
    version_tarifa: int
    cobertura_meses: int
    coberturas: list[CoberturaPrecioOut]
    vigencia_cotizacion: VigenciaOut
    creada_en: datetime
