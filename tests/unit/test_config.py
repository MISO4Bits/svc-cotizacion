from __future__ import annotations

from app.config import Settings, get_settings


def test_settings_por_defecto():
    s = Settings()
    assert s.service_name == "svc-cotizacion"
    assert s.environment == "local"
    assert s.adapters == "fake"
    assert s.cache_backend == "memory"
    assert s.perfil_cache_ttl_seconds == 43200
    assert s.pubsub_subscription == "cotizacion-consentimiento-revocado"


def test_settings_lee_prefijo_cot(monkeypatch):
    monkeypatch.setenv("COT_ADAPTERS", "sql")
    assert Settings().adapters == "sql"


def test_get_settings_cachea():
    assert get_settings() is get_settings()


def test_settings_de_persistencia_y_tarifa_por_defecto():
    s = Settings()
    assert s.repository_backend == "memory"
    assert s.tarifa_cache_ttl_seconds == 86400
    assert s.productos_retries == 1
