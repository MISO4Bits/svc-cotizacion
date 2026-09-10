from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración por variables de entorno (prefijo ``COT_``)."""

    model_config = SettingsConfigDict(env_prefix="COT_", env_file=".env", extra="ignore")

    service_name: str = "svc-cotizacion"
    environment: str = "local"

    # Adaptadores de salida: "fake" (todo en memoria) | "sql" (persistencia real) | "http".
    # Cada modo se implementa en su fase correspondiente de la ruta de construcción.
    adapters: str = "fake"


@lru_cache
def get_settings() -> Settings:
    return Settings()
