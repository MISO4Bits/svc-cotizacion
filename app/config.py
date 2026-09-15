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

    # Modo "http": adaptador resiliente hacia Perfilamiento (EXP-02).
    perfilamiento_base_url: str = "http://localhost:8089"
    http_timeout_seconds: float = 0.7  # timeout duro por llamada (BITS-80 / EXP-02)
    http_retries: int = 0
    circuit_fail_max: int = 5
    circuit_reset_timeout_seconds: int = 30

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
