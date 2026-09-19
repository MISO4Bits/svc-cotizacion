"""Pruebas del despacho de eventos (app.consumidores) — sin GCP."""

from __future__ import annotations

from decimal import Decimal

from app.adapters.fakes import FakeCache
from app.consumidores import despachar_evento
from app.domain import DomainEvent, EfectoFactor, FactorRiesgo, NivelRiesgo, PerfilRiesgo


async def test_consentimiento_revocado_invalida_el_cache():
    cache = FakeCache()
    await cache.guardar(
        "cli-1",
        PerfilRiesgo(
            nivel_riesgo=NivelRiesgo.BAJO,
            factores=(FactorRiesgo("x", EfectoFactor.POSITIVO),),
            factor_ajuste=Decimal("0.9"),
        ),
    )
    evento = DomainEvent("ConsentimientoRevocado", {"clienteId": "cli-1", "scope": "OPEN_FINANCE"})

    await despachar_evento(cache, evento)

    assert await cache.obtener("cli-1") is None


async def test_consentimiento_revocado_de_cliente_sin_cache_no_lanza():
    cache = FakeCache()
    evento = DomainEvent("ConsentimientoRevocado", {"clienteId": "no-cacheado"})

    await despachar_evento(cache, evento)  # no debe lanzar


async def test_tipo_de_evento_no_reconocido_no_hace_nada():
    cache = FakeCache()
    await cache.guardar(
        "cli-1",
        PerfilRiesgo(nivel_riesgo=NivelRiesgo.MEDIO, factores=(), factor_ajuste=Decimal("1")),
    )
    evento = DomainEvent("OtroEvento", {"clienteId": "cli-1"})

    await despachar_evento(cache, evento)

    assert await cache.obtener("cli-1") is not None
