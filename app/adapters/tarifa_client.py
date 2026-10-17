"""Adaptador HTTP hacia Productos y Configuración (implementa ``TarifaPort``).

  GET {base}/v1/tarifas/vida-hipotecario?mercado=CO
  200: { mercado, producto, version, franjas: [{ edadDesde, edadHasta, tasaMensualPorMil }] }

Solo se llama cuando la tarifa no está en caché (ver ``tarifa_cache.py``). Productos es
back-office y está aislado por disponibilidad: si no responde, ``DependenciaNoDisponible``
y la cotización falla con 503 — no hay una tarifa de reemplazo.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.domain import DependenciaNoDisponible, FranjaTarifa, Tarifa
from app.resilience import ResilientHttpClient

logger = logging.getLogger("cotizacion.adapters.tarifa")

MERCADO = "CO"


class TarifaClient:
    def __init__(self, http: ResilientHttpClient, mercado: str = MERCADO) -> None:
        self._http = http
        self._mercado = mercado

    async def aclose(self) -> None:
        await self._http.aclose()

    async def obtener(self) -> Tarifa:
        resp = await self._http.request(
            "GET", "/v1/tarifas/vida-hipotecario", params={"mercado": self._mercado}
        )
        if resp.status_code != 200:
            logger.warning("productos respondio con error status_code=%s", resp.status_code)
            raise DependenciaNoDisponible(f"Productos respondió {resp.status_code}")
        tarifa = tarifa_desde_dict(resp.json())
        logger.info("tarifa obtenida de productos version=%s", tarifa.version)
        return tarifa


def tarifa_desde_dict(data: dict) -> Tarifa:
    """Parsea la tarifa recibida de Productos — reusado por ``redis_cache.py`` para
    deserializarla desde el caché, misma forma exacta de JSON."""
    return Tarifa(
        version=int(data["version"]),
        franjas=tuple(
            FranjaTarifa(
                edad_desde=int(f["edadDesde"]),
                edad_hasta=int(f["edadHasta"]),
                tasa_mensual_por_mil=Decimal(str(f["tasaMensualPorMil"])),
            )
            for f in data["franjas"]
        ),
    )


def tarifa_a_dict(tarifa: Tarifa) -> dict:
    return {
        "version": tarifa.version,
        "franjas": [
            {
                "edadDesde": f.edad_desde,
                "edadHasta": f.edad_hasta,
                "tasaMensualPorMil": str(f.tasa_mensual_por_mil),
            }
            for f in tarifa.franjas
        ],
    }
