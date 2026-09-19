"""Despacho de eventos de dominio consumidos desde Pub/Sub.

Aislado de la mecánica de transporte (Pub/Sub, ver
``adapters/pubsub_consumer.py``) a propósito: esta función es pura respecto
del evento ya decodificado, así que se prueba sin credenciales de GCP ni
infraestructura real.

CoreTransaccional publica ``ConsentimientoRevocado`` al revocar
consentimiento (ver ``svc-core/app/services.py``). Cotización lo consume
únicamente para invalidar su caché de perfiles — el cálculo/invalidación
del perfil en sí lo hace Perfilamiento, que consume el mismo evento por su
lado (suscripción independiente sobre el mismo tópico compartido).
"""

from __future__ import annotations

import logging

from app.domain import DomainEvent
from app.ports import CachePort

logger = logging.getLogger("cotizacion.consumidores")


async def despachar_evento(cache: CachePort, evento: DomainEvent) -> None:
    if evento.tipo == "ConsentimientoRevocado":
        cliente_id = evento.datos["clienteId"]
        logger.info(
            "despachar_evento: ConsentimientoRevocado cliente_id=%s -> invalidando caché",
            cliente_id,
        )
        await cache.eliminar(cliente_id)
        return

    # El filtro de la suscripción (iac-gcp-dev/modules/pubsub) ya deja
    # pasar solo este tipo — llegar aquí es señal de que el filtro y este
    # despacho se desalinearon.
    logger.warning("despachar_evento: tipo de evento no reconocido tipo=%s", evento.tipo)
