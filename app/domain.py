"""Modelo de dominio del servicio de Cotización.

DTO de dominio (dataclasses congeladas, sin framework) + errores de aplicación.
La validación de JSON de entrada vive en ``api/schemas.py`` (Pydantic); acá solo
van los tipos del dominio y sus invariantes de consistencia.

Modelo: seguro de vida sobre crédito hipotecario (BITS-95). Diseño de referencia:
página "Cotización y Rating" de David (Confluence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

PRODUCTO = "VIDA_HIPOTECARIO"


# --- errores de aplicación (se traducen a RFC 9457 en la capa API) ---


class CotError(Exception):
    status = 500
    title = "Error interno"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail


class SolicitudInvalida(CotError):
    status = 400
    title = "Solicitud inválida"


class RecursoNoEncontrado(CotError):
    status = 404
    title = "Recurso no encontrado"


class ReglaNegocio(CotError):
    status = 422
    title = "Regla de negocio no satisfecha"


class DependenciaNoDisponible(CotError):
    status = 503
    title = "Dependencia no disponible"


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class DomainEvent:
    """Evento de dominio recibido del tópico compartido (ver
    iac-gcp-dev/modules/pubsub). Cotización solo consume — hoy únicamente
    ``ConsentimientoRevocado``, para invalidar el caché de perfiles (ver
    adapters/consumidores.py)."""

    tipo: str
    datos: dict[str, Any]
    id: str = field(default_factory=new_id)
    ocurrido_en: datetime = field(default_factory=now_utc)


# --- enumeraciones del dominio ---


class ActividadFisica(StrEnum):
    NUNCA = "NUNCA"
    OCASIONAL = "OCASIONAL"
    REGULAR = "REGULAR"


class NivelRiesgo(StrEnum):
    BAJO = "BAJO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"


class EstadoCotizacion(StrEnum):
    VIGENTE = "VIGENTE"
    EXPIRADA = "EXPIRADA"


class EfectoFactor(StrEnum):
    POSITIVO = "POSITIVO"
    NEGATIVO = "NEGATIVO"


class Moneda(StrEnum):
    COP = "COP"


# --- datos de entrada ---


@dataclass(frozen=True)
class DatosCredito:
    valor_credito: Decimal
    plazo_meses: int
    edad: int
    entidad_acreedora: str
    saldo_insoluto: Decimal


@dataclass(frozen=True)
class CuestionarioHabitos:
    consume_tabaco: bool
    actividad_fisica: ActividadFisica
    condiciones_preexistentes: bool
    dependientes_economicos: int


@dataclass(frozen=True)
class SolicitudCotizacion:
    cliente_id: str
    datos_credito: DatosCredito
    cuestionario_habitos: CuestionarioHabitos


# --- perfil de riesgo (lo devuelve PerfilRiesgoPort) ---


@dataclass(frozen=True)
class FactorRiesgo:
    descripcion: str
    efecto: EfectoFactor
    peso_relativo: Decimal | None = None


@dataclass(frozen=True)
class PerfilRiesgo:
    nivel_riesgo: NivelRiesgo
    factores: tuple[FactorRiesgo, ...]
    factor_ajuste: Decimal  # multiplicador que el rating aplica a la prima base
    fuentes_no_disponibles: tuple[str, ...] = ()


# --- resultado ---


@dataclass(frozen=True)
class Oferta:
    prima_mensual: Decimal
    prima_base_mensual: Decimal
    suma_asegurada: Decimal
    cobertura_meses: int
    moneda: Moneda
    personalizado: bool
    fuentes_no_disponibles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for nombre, valor in (
            ("prima_mensual", self.prima_mensual),
            ("prima_base_mensual", self.prima_base_mensual),
            ("suma_asegurada", self.suma_asegurada),
        ):
            if valor < 0:
                raise ReglaNegocio(f"{nombre} no puede ser negativo")
        if not self.personalizado and self.prima_mensual != self.prima_base_mensual:
            raise ReglaNegocio("sin personalización, la prima debe ser igual a la prima base")


@dataclass(frozen=True)
class Vigencia:
    desde: datetime
    hasta: datetime

    def __post_init__(self) -> None:
        if self.desde >= self.hasta:
            raise ReglaNegocio("la vigencia 'desde' debe ser anterior a 'hasta'")


@dataclass(frozen=True)
class Cotizacion:
    id: str
    cliente_id: str
    estado: EstadoCotizacion
    oferta: Oferta
    perfil_riesgo: PerfilRiesgo | None
    vigencia: Vigencia
    creada_en: datetime
    producto: str = PRODUCTO

    def __post_init__(self) -> None:
        if self.oferta.personalizado and self.perfil_riesgo is None:
            raise ReglaNegocio("una cotización personalizada debe incluir el perfil de riesgo")
        if not self.oferta.personalizado and self.perfil_riesgo is not None:
            raise ReglaNegocio("una cotización no personalizada no debe incluir perfil de riesgo")
