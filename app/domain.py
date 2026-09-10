"""Modelo de dominio del servicio de Cotización: errores de aplicación.

Los DTO (``SolicitudCotizacion``, ``Cotizacion``, ...) se agregan en la Fase B.
La jerarquía de errores se traduce a RFC 9457 (Problem Details) en la capa API.
"""

from __future__ import annotations


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
