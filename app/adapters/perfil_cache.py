"""Decorador cache-aside sobre ``PerfilRiesgoPort``: evita pagar la llamada
de red a Perfilamiento en cada cotización — el perfil de un cliente no
cambia salvo que otorgue/revoque consentimiento otra vez, y la revocación
ya invalida el caché por evento (ver ``adapters/pubsub_consumer.py`` +
``consumidores.py``). El TTL del ``CachePort`` es solo la red de seguridad
si ese mensaje se pierde, no el mecanismo principal.

No cachea "perfil no encontrado" (``None``): un cliente que acaba de
otorgar consentimiento debe poder ver su perfil personalizado en la
SIGUIENTE cotización que pida, no quedar atascado en "sin perfil" hasta
que expire un caché negativo.
"""

from __future__ import annotations

import logging

from app.domain import PerfilRiesgo
from app.ports import CachePort, PerfilRiesgoPort

logger = logging.getLogger("cotizacion.adapters.perfil_cache")


class PerfilRiesgoCacheado:
    def __init__(self, interno: PerfilRiesgoPort, cache: CachePort) -> None:
        self._interno = interno
        self._cache = cache

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        perfil = await self._cache.obtener(cliente_id)
        if perfil is not None:
            logger.info("perfil_cache: hit cliente_id=%s", cliente_id)
            return perfil

        logger.info("perfil_cache: miss cliente_id=%s, consultando Perfilamiento", cliente_id)
        perfil = await self._interno.obtener_perfil(cliente_id)
        if perfil is not None:
            await self._cache.guardar(cliente_id, perfil)
        return perfil

    async def aclose(self) -> None:
        cerrar = getattr(self._interno, "aclose", None)
        if cerrar is not None:
            await cerrar()
