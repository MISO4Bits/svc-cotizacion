"""Modelo de dominio del servicio de Cotización.

DTO de dominio (dataclasses congeladas, sin framework) + errores de aplicación.
La validación de JSON de entrada vive en ``api/schemas.py`` (Pydantic); acá solo
van los tipos del dominio y sus invariantes de consistencia.

Modelo: seguro de vida sobre crédito hipotecario (BITS-95). Diseño de referencia:
página "Cotización y Rating" de David (Confluence).
"""

from __future__ import annotations

import re
import unicodedata
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

    def __init__(self, detail: str | None = None, errores: list[dict[str, str]] | None = None):
        super().__init__(detail or self.title)
        self.detail = detail
        self.errores = errores or []


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
    """Evento de dominio del tópico compartido (ver iac-gcp-dev/modules/pubsub). Cotización
    consume ``ConsentimientoRevocado`` y los de Perfilamiento para invalidar el caché de perfiles
    (ver consumidores.py) y publica ``CotizacionCreada`` y ``CotizacionEliminada`` para que Core
    borre la póliza pendiente de la cotización anterior (BITS-101)."""

    tipo: str
    datos: dict[str, Any]
    id: str = field(default_factory=new_id)
    ocurrido_en: datetime = field(default_factory=now_utc)


# --- enumeraciones del dominio ---


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


class OrigenDatos(StrEnum):
    """De dónde salen los datos del crédito.

    ``CONFIRMADO``: coinciden exactamente con una hipoteca que Open Finance reportó a
    Perfilamiento (BITS-101). ``DECLARADO``: los escribió el cliente, o no hay con qué compararlos.
    """

    CONFIRMADO = "CONFIRMADO"
    DECLARADO = "DECLARADO"


# --- datos de entrada ---

EDAD_MINIMA = 18
EDAD_MAXIMA = 65
# La póliza permite ingresar hasta los 65 años y permanecer hasta los 75.
EDAD_MAXIMA_AL_TERMINAR = 75


@dataclass(frozen=True)
class DatosCredito:
    valor_credito: Decimal
    plazo_restante_meses: int
    entidad_acreedora: str
    saldo_insoluto: Decimal


def clave_entidad(nombre: str) -> str:
    """Forma comparable del nombre de una entidad: sin tildes, mayúsculas ni puntuación y sin el
    sufijo societario, para que ``BANCO DE BOGOTÁ S.A.`` y ``Banco de Bogotá`` coincidan."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", sin_tildes.lower())
    if tokens[-2:] == ["s", "a"]:
        tokens = tokens[:-2]
    elif tokens[-1:] == ["sa"]:
        tokens = tokens[:-1]
    return " ".join(tokens)


@dataclass(frozen=True)
class SolicitudCotizacion:
    """``edad`` ya viene calculada: la deriva el BFF de la fecha de nacimiento del registro."""

    cliente_id: str
    edad: int
    datos_credito: DatosCredito


# --- tarifa (la entrega Productos y Configuración) ---


@dataclass(frozen=True)
class FranjaTarifa:
    edad_desde: int
    edad_hasta: int
    tasa_mensual_por_mil: Decimal


@dataclass(frozen=True)
class TarifaHogar:
    """Cobertura opcional de Hogar: tarifa fija. La suma asegurada es
    ``min(suma_asegurada_maxima, valor del crédito)``; ``iva`` es una fracción (0,19)."""

    tasa_mensual_por_mil: Decimal
    suma_asegurada_maxima: Decimal
    iva: Decimal


@dataclass(frozen=True)
class Tarifa:
    """Tasa mensual por cada $1.000 de saldo según la edad (Vida) y tarifa de Hogar, entregadas
    por Productos en una sola llamada. ``version`` identifica la tarifa con la que se calculó
    cada cotización."""

    version: int
    franjas: tuple[FranjaTarifa, ...]
    hogar: TarifaHogar

    def tasa_para(self, edad: int) -> Decimal:
        for franja in self.franjas:
            if franja.edad_desde <= edad <= franja.edad_hasta:
                return franja.tasa_mensual_por_mil
        raise ReglaNegocio(f"La tarifa no tiene una franja para la edad {edad}")


# --- perfil de riesgo (lo devuelve PerfilRiesgoPort) ---


@dataclass(frozen=True)
class FactorRiesgo:
    descripcion: str
    efecto: EfectoFactor
    peso_relativo: Decimal | None = None


@dataclass(frozen=True)
class Hipoteca:
    """Una hipoteca que Open Finance reportó (lo que viaja en el perfil de Perfilamiento)."""

    entidad_acreedora: str
    valor_credito: Decimal
    saldo_insoluto: Decimal
    plazo_restante_meses: int


@dataclass(frozen=True)
class PerfilRiesgo:
    nivel_riesgo: NivelRiesgo
    factores: tuple[FactorRiesgo, ...]
    factor_ajuste: Decimal  # multiplicador que el rating aplica a la prima base
    fuentes_no_disponibles: tuple[str, ...] = ()
    hipotecas: tuple[Hipoteca, ...] = ()


def coincide_con_hipoteca(datos: DatosCredito, hipotecas: tuple[Hipoteca, ...]) -> bool:
    """``True`` si el crédito declarado es exactamente una de las hipotecas reportadas: entidad
    (comparada sin tildes, mayúsculas ni sufijo societario), valor, saldo y plazo."""
    entidad = clave_entidad(datos.entidad_acreedora)
    return any(
        clave_entidad(h.entidad_acreedora) == entidad
        and h.valor_credito == datos.valor_credito
        and h.saldo_insoluto == datos.saldo_insoluto
        and h.plazo_restante_meses == datos.plazo_restante_meses
        for h in hipotecas
    )


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


class CodigoCobertura(StrEnum):
    VIDA = "VIDA"
    HOGAR = "HOGAR"


@dataclass(frozen=True)
class CoberturaPrecio:
    """Precio mensual de una cobertura. ``prima_total = prima_neta + iva``."""

    codigo: CodigoCobertura
    obligatoria: bool
    suma_asegurada: Decimal
    prima_neta: Decimal
    iva: Decimal

    def __post_init__(self) -> None:
        for nombre, valor in (
            ("suma_asegurada", self.suma_asegurada),
            ("prima_neta", self.prima_neta),
            ("iva", self.iva),
        ):
            if valor < 0:
                raise ReglaNegocio(f"{nombre} no puede ser negativo")

    @property
    def prima_total(self) -> Decimal:
        return self.prima_neta + self.iva


@dataclass(frozen=True)
class Vigencia:
    desde: datetime
    hasta: datetime

    def __post_init__(self) -> None:
        if self.desde >= self.hasta:
            raise ReglaNegocio("la vigencia 'desde' debe ser anterior a 'hasta'")


@dataclass(frozen=True)
class Cotizacion:
    """La cotización activa de un cliente: es única, no tiene id propio y una nueva la reemplaza.

    Guarda una foto de todo lo usado para calcular el precio (edad, datos del crédito, tasa y
    versión de la tarifa, factor del perfil) para poder reconstruirlo aunque después cambien.
    ``hogar`` es el precio de la cobertura opcional de Hogar tal como se calculó con esa tarifa;
    es ``None`` solo en cotizaciones guardadas antes de que existiera.
    """

    cliente_id: str
    edad: int
    datos_credito: DatosCredito
    origen_datos: OrigenDatos
    tasa: Decimal
    version_tarifa: int
    oferta: Oferta
    perfil_riesgo: PerfilRiesgo | None
    vigencia: Vigencia
    creada_en: datetime
    producto: str = PRODUCTO
    hogar: CoberturaPrecio | None = None

    def __post_init__(self) -> None:
        if self.oferta.personalizado and self.perfil_riesgo is None:
            raise ReglaNegocio("una cotización personalizada debe incluir el perfil de riesgo")
        if not self.oferta.personalizado and self.perfil_riesgo is not None:
            raise ReglaNegocio("una cotización no personalizada no debe incluir perfil de riesgo")

    def estado_en(self, ahora: datetime) -> EstadoCotizacion:
        """``EXPIRADA`` pasada la vigencia. Se deriva al leer: no hay tareas que la actualicen."""
        if ahora >= self.vigencia.hasta:
            return EstadoCotizacion.EXPIRADA
        return EstadoCotizacion.VIGENTE
