"""Pruebas del decorador cache-aside (app.adapters.perfil_cache) — sin
Redis real, con FakeCache."""

from __future__ import annotations

from decimal import Decimal

from app.adapters.fakes import FakeCache
from app.adapters.perfil_cache import PerfilRiesgoCacheado
from app.domain import EfectoFactor, FactorRiesgo, NivelRiesgo, PerfilRiesgo

_PERFIL = PerfilRiesgo(
    nivel_riesgo=NivelRiesgo.BAJO,
    factores=(FactorRiesgo("Actividad física regular", EfectoFactor.POSITIVO),),
    factor_ajuste=Decimal("0.90"),
)


class _PerfiladorEspia:
    def __init__(self, perfil: PerfilRiesgo | None = _PERFIL) -> None:
        self._perfil = perfil
        self.llamadas = 0

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        self.llamadas += 1
        return self._perfil


async def test_miss_consulta_al_interno_y_guarda_en_cache():
    interno = _PerfiladorEspia()
    cache = FakeCache()
    cacheado = PerfilRiesgoCacheado(interno, cache)

    perfil = await cacheado.obtener_perfil("cli-1")

    assert perfil == _PERFIL
    assert interno.llamadas == 1
    assert await cache.obtener("cli-1") == _PERFIL


async def test_hit_no_vuelve_a_llamar_al_interno():
    interno = _PerfiladorEspia()
    cache = FakeCache()
    await cache.guardar("cli-1", _PERFIL)
    cacheado = PerfilRiesgoCacheado(interno, cache)

    perfil = await cacheado.obtener_perfil("cli-1")

    assert perfil == _PERFIL
    assert interno.llamadas == 0


async def test_perfil_no_encontrado_no_se_cachea():
    """Un cliente que acaba de otorgar consentimiento no debe quedar
    atascado en "sin perfil" — cada llamada mientras no exista perfil
    vuelve a consultar al interno, nunca cachea el None."""
    interno = _PerfiladorEspia(perfil=None)
    cache = FakeCache()
    cacheado = PerfilRiesgoCacheado(interno, cache)

    assert await cacheado.obtener_perfil("cli-1") is None
    assert await cacheado.obtener_perfil("cli-1") is None
    assert interno.llamadas == 2
    assert await cache.obtener("cli-1") is None


async def test_aclose_delega_al_interno():
    class _ConAclose(_PerfiladorEspia):
        def __init__(self) -> None:
            super().__init__()
            self.cerrado = False

        async def aclose(self) -> None:
            self.cerrado = True

    interno = _ConAclose()
    cacheado = PerfilRiesgoCacheado(interno, FakeCache())
    await cacheado.aclose()
    assert interno.cerrado is True
