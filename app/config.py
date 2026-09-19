from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno (prefijo ``COT_``)."""

    model_config = SettingsConfigDict(env_prefix="COT_", env_file=".env", extra="ignore")

    service_name: str = "svc-cotizacion"
    environment: str = "local"

    # Adaptadores de salida: "fake" (todo en memoria) | "http" (Perfilamiento real).
    adapters: str = "fake"

    # Modo "http": adaptador resiliente hacia Perfilamiento (EXP-02). El
    # contrato es una lectura (GET /perfiles/{clienteId}, ver Confluence ›
    # página Perfilamiento, Sección 8, decisión 2026-09-18) — ya no una
    # petición de cómputo en caliente, por eso el timeout bajó de 700ms
    # (viejo presupuesto, cuando Perfilamiento calculaba contra Open
    # Finance/Open Data dentro del propio request) a uno acorde a una
    # lectura de repositorio.
    perfilamiento_base_url: str = "http://localhost:8089"
    http_timeout_seconds: float = 0.2
    http_retries: int = 0
    circuit_fail_max: int = 5
    circuit_reset_timeout_seconds: int = 30

    # Caché de perfiles: "memory" (default, local/tests) | "redis" (real —
    # pod dentro del cluster, ver deploy/apps/redis; decisión 2026-09-19).
    # Independiente de `adapters`: evita pagar la llamada de red a
    # Perfilamiento en cada cotización. La invalidación principal es por
    # evento (ConsentimientoRevocado, ver adapters/pubsub_consumer.py, solo
    # arranca con cache_backend="redis"); el TTL es la red de seguridad si
    # ese mensaje se pierde.
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    perfil_cache_ttl_seconds: int = 43200  # 12h

    # Consumo de ConsentimientoRevocado (solo para invalidar el caché de
    # arriba) — mismo tópico compartido con CoreTransaccional/Perfilamiento
    # (ver iac-gcp-dev/modules/pubsub).
    pubsub_project_id: str | None = None
    pubsub_subscription: str = "cotizacion-consentimiento-revocado"

    # Observabilidad (DI-008): OTLP/gRPC hacia Grafana Alloy dentro del
    # cluster. Deshabilitado por defecto — en local/tests no hay receptor
    # escuchando; se habilita vía COT_OTEL_ENABLED=true en el manifiesto de
    # despliegue.
    otel_enabled: bool = False
    otel_exporter_endpoint: str = (
        "k8s-monitoring-alloy-receiver.observability.svc.cluster.local:4317"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
