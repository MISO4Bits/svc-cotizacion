"""Adaptador de producción: publica ``CotizacionCreada`` y ``CotizacionEliminada`` en el tópico
compartido de Google Cloud Pub/Sub (ver iac-gcp-dev/modules/pubsub). El tipo del evento va como
atributo del mensaje (``tipo``), igual que en Core y Perfilamiento.

No espera el acuse del servidor: ``publish()`` encola el mensaje y devuelve enseguida, así que
cotizar no paga la latencia de Pub/Sub. Si el envío falla, solo se registra; Core tiene otra vía
para borrar la póliza pendiente (al crear una solicitud nueva).

Fuera del alcance de las pruebas locales (requiere credenciales e infraestructura GCP). Se
excluye de la medición de cobertura.
"""

from __future__ import annotations

import json
import logging

from opentelemetry import propagate

from app.domain import DomainEvent

logger = logging.getLogger("cotizacion.adapters.pubsub_publisher")


class PubSubEventPublisher:  # pragma: no cover
    def __init__(self, project_id: str, topic: str) -> None:
        from google.cloud import pubsub_v1

        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project_id, topic)

    async def publicar(self, evento: DomainEvent) -> None:
        payload = json.dumps(
            {
                "tipo": evento.tipo,
                "id": evento.id,
                "ocurridoEn": evento.ocurrido_en.isoformat(),
                "datos": evento.datos,
            }
        ).encode("utf-8")
        atributos = {"tipo": evento.tipo}
        propagate.inject(atributos)
        futuro = self._publisher.publish(self._topic_path, payload, **atributos)
        futuro.add_done_callback(lambda f: self._registrar(evento, f))

    @staticmethod
    def _registrar(evento: DomainEvent, futuro) -> None:
        try:
            message_id = futuro.result()
        except Exception:
            logger.exception("no se pudo publicar el evento tipo=%s id=%s", evento.tipo, evento.id)
            return
        logger.info(
            "evento_publicado: tipo=%s id=%s message_id=%s", evento.tipo, evento.id, message_id
        )
