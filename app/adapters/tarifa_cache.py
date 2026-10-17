"""Decorador cache-aside sobre ``TarifaPort``: la tabla de tasas casi no cambia, así que se
llama a Productos una sola vez y las siguientes cotizaciones la leen del caché.

No hay invalidación por evento: cambiar la tarifa es editar la semilla de Productos y
desplegar; el caché se refresca con su TTL (24 h) o borrando la clave a mano.

Si varias cotizaciones llegan con el caché vacío, un candado deja que solo una vaya a Productos
y las demás esperen su resultado (una sola llamada por pod, no una por cotización).
"""

from __future__ import annotations

import asyncio
import logging

from app.domain import Tarifa
from app.ports import TarifaCachePort, TarifaPort

logger = logging.getLogger("cotizacion.adapters.tarifa_cache")


class TarifaCacheada:
    def __init__(self, interno: TarifaPort, cache: TarifaCachePort) -> None:
        self._interno = interno
        self._cache = cache
        self._candado = asyncio.Lock()

    async def obtener(self) -> Tarifa:
        tarifa = await self._cache.obtener()
        if tarifa is not None:
            return tarifa

        async with self._candado:
            # Otra cotización pudo llenar el caché mientras esta esperaba el candado.
            tarifa = await self._cache.obtener()
            if tarifa is not None:
                return tarifa
            logger.info("tarifa_cache: miss, consultando Productos")
            tarifa = await self._interno.obtener()
            await self._cache.guardar(tarifa)
            return tarifa

    async def aclose(self) -> None:
        cerrar = getattr(self._interno, "aclose", None)
        if cerrar is not None:
            await cerrar()
