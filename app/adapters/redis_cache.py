"""Adaptador de producción del ``CachePort``: Redis desplegado como pod
dentro del mismo cluster (ver ``deploy/apps/redis``) — decisión 2026-09-19,
solo un acelerador de latencia para el camino Cotización -> Perfilamiento,
nunca la fuente de verdad (esa sigue siendo Perfilamiento/Spanner). Sin
autenticación: el pod no se expone fuera del cluster, mismo criterio que
``deploy/apps/wiremock``.

Cualquier fallo de Redis se trata como cache miss (``obtener``) o se
absorbe en silencio (``guardar``/``eliminar``) — nunca debe romper el
camino principal de crear una cotización; degradar a "sin caché, llama
directo a Perfilamiento" es aceptable, tumbar la cotización no.

Fuera del alcance de las pruebas locales (requiere un Redis real). Se
excluye de la medición de cobertura.
"""

from __future__ import annotations

import json
import logging

from app.adapters.perfilador_client import perfil_desde_dict
from app.domain import PerfilRiesgo

logger = logging.getLogger("cotizacion.adapters.redis_cache")

_PREFIJO = "perfil:"


class RedisCache:  # pragma: no cover
    def __init__(self, url: str, ttl_seconds: int) -> None:
        import redis.asyncio as redis

        self._client = redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    async def obtener(self, cliente_id: str) -> PerfilRiesgo | None:
        try:
            crudo = await self._client.get(_PREFIJO + cliente_id)
        except Exception:
            logger.exception(
                "redis_cache: fallo leyendo cliente_id=%s, se trata como miss", cliente_id
            )
            return None
        if crudo is None:
            return None
        return perfil_desde_dict(json.loads(crudo))

    async def guardar(self, cliente_id: str, perfil: PerfilRiesgo) -> None:
        try:
            await self._client.set(_PREFIJO + cliente_id, json.dumps(_a_dict(perfil)), ex=self._ttl)
        except Exception:
            logger.exception(
                "redis_cache: fallo guardando cliente_id=%s (no bloquea la cotización)", cliente_id
            )

    async def eliminar(self, cliente_id: str) -> None:
        try:
            await self._client.delete(_PREFIJO + cliente_id)
        except Exception:
            logger.exception("redis_cache: fallo invalidando cliente_id=%s", cliente_id)

    async def aclose(self) -> None:
        await self._client.aclose()


def _a_dict(perfil: PerfilRiesgo) -> dict:
    return {
        "nivelRiesgo": str(perfil.nivel_riesgo),
        "factorAjuste": str(perfil.factor_ajuste),
        "factores": [
            {
                "descripcion": f.descripcion,
                "efecto": str(f.efecto),
                "pesoRelativo": str(f.peso_relativo) if f.peso_relativo is not None else None,
            }
            for f in perfil.factores
        ],
        "fuentesNoDisponibles": list(perfil.fuentes_no_disponibles),
    }
