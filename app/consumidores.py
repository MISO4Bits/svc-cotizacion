"""Despacho de eventos de dominio consumidos desde Pub/Sub.

Aislado de la mecánica de transporte (Pub/Sub, ver
``adapters/pubsub_consumer.py``) a propósito: esta función es pura respecto
del evento ya decodificado, así que se prueba sin credenciales de GCP ni
infraestructura real.

CoreTransaccional publica ``ConsentimientoRevocado`` al revocar
consentimiento (ver ``svc-core/app/services.py``) y Perfilamiento publica
``PerfilCalculado``/``PerfilInvalidado`` cada vez que recalcula o borra un
perfil. Cotización los consume únicamente para invalidar su caché de perfiles:
el cálculo del perfil en sí lo hace Perfilamiento, que consume el evento de
Core por su lado (suscripción independiente sobre el mismo tópico compartido).

Invalidar también con los eventos de Perfilamiento cubre la carrera de la
revocación: si Cotización invalida al recibir ``ConsentimientoRevocado`` pero
Perfilamiento aún no recalculó, una lectura en ese intervalo guardaría de nuevo
el perfil viejo; el siguiente evento de Perfilamiento lo vuelve a invalidar.
"""

from __future__ import annotations

import logging

from app.domain import DomainEvent
from app.ports import CachePort

logger = logging.getLogger("cotizacion.consumidores")


TIPOS_QUE_INVALIDAN = frozenset({"ConsentimientoRevocado", "PerfilCalculado", "PerfilInvalidado"})


async def despachar_evento(cache: CachePort, evento: DomainEvent) -> None:
    if evento.tipo in TIPOS_QUE_INVALIDAN:
        cliente_id = evento.datos["clienteId"]
        logger.info(
            "despachar_evento: %s cliente_id=%s -> invalidando caché", evento.tipo, cliente_id
        )
        await cache.eliminar(cliente_id)
        return

    # El filtro de la suscripción (iac-gcp-dev/modules/pubsub) ya deja
    # pasar solo estos tipos — llegar aquí es señal de que el filtro y este
    # despacho se desalinearon.
    logger.warning("despachar_evento: tipo de evento no reconocido tipo=%s", evento.tipo)
