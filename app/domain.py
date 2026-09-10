"""Modelo de dominio del servicio de Cotización.

DTO de dominio (dataclasses congeladas, sin framework) + errores de aplicación.
La validación de JSON de entrada vive en ``api/schemas.py`` (Pydantic); las reglas
del cálculo viven en ``services.py``. Acá solo van los tipos del dominio y sus
invariantes básicas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

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


# --- enumeraciones del dominio ---


class Ramo(StrEnum):
    PROTECCION_DISPOSITIVO = "PROTECCION_DISPOSITIVO"


class TipoCanal(StrEnum):
    SOCIO = "SOCIO"
    ASESOR = "ASESOR"


class TipoDispositivo(StrEnum):
    CELULAR = "CELULAR"
    PORTATIL = "PORTATIL"
    TABLET = "TABLET"


class Moneda(StrEnum):
    COP = "COP"


class EstadoCotizacion(StrEnum):
    VIGENTE = "VIGENTE"
    EXPIRADA = "EXPIRADA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


# --- datos de entrada ---


@dataclass(frozen=True)
class Canal:
    tipo: TipoCanal
    socio_id: str


@dataclass(frozen=True)
class Dispositivo:
    tipo: TipoDispositivo
    valor_asegurado: Decimal
    antiguedad_meses: int


@dataclass(frozen=True)
class Solicitante:
    edad: int
    pais: str


@dataclass(frozen=True)
class SolicitudCotizacion:
    ramo: Ramo
    canal: Canal
    dispositivo: Dispositivo
    solicitante: Solicitante


# --- resultado ---


@dataclass(frozen=True)
class PrimaDesglose:
    prima_pura: Decimal
    gastos: Decimal
    impuestos: Decimal
    total: Decimal
    moneda: Moneda = Moneda.COP

    def __post_init__(self) -> None:
        for nombre, valor in (
            ("prima_pura", self.prima_pura),
            ("gastos", self.gastos),
            ("impuestos", self.impuestos),
        ):
            if valor < 0:
                raise ReglaNegocio(f"{nombre} no puede ser negativo")
        suma = self.prima_pura + self.gastos + self.impuestos
        if self.total != suma:
            raise ReglaNegocio(
                f"el total de la prima ({self.total}) no coincide "
                f"con la suma de sus partes ({suma})"
            )


@dataclass(frozen=True)
class Cobertura:
    codigo: str
    nombre: str
    suma_asegurada: Decimal
    deducible: Decimal


@dataclass(frozen=True)
class Tarifa:
    """Factores de tarifa vigentes para un ramo, provistos por la dependencia de tarifación.

    El motor de rating (en ``services.py``) combina la solicitud con esta tarifa
    para producir la ``PrimaDesglose`` y las coberturas de la cotización.
    """

    ramo: Ramo
    tasa_base_anual: Decimal  # proporción del valor asegurado, por año de vigencia
    recargo_gastos: Decimal  # proporción de gastos sobre la prima pura
    tasa_impuesto: Decimal  # proporción de impuesto sobre (prima pura + gastos)
    coberturas: tuple[Cobertura, ...]


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
    estado: EstadoCotizacion
    ramo: Ramo
    prima: PrimaDesglose
    coberturas: tuple[Cobertura, ...]
    vigencia: Vigencia
    creada_en: datetime

    def __post_init__(self) -> None:
        if not self.coberturas:
            raise ReglaNegocio("una cotización debe tener al menos una cobertura")
