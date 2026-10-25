"""Adaptador HTTP hacia el servicio de Perfilamiento (implementa PerfilRiesgoPort).

Lee el perfil ya calculado de forma asíncrona (disparado por consentimiento,
ver Confluence › página Perfilamiento, Sección 8, decisión 2026-09-18) — ya
no se le pide a Perfilamiento que calcule nada en caliente:

  GET {base}/v1/perfiles/{clienteId}
  200: { nivelRiesgo, factorAjuste, factores[], fuentesNoDisponibles[] }
  404: perfil no calculado todavía (consentimiento no otorgado, o el
       evento aún no se procesó) — no es un fallo, ``CotizacionService``
       cae a tarifa estándar igual que con ``DependenciaNoDisponible``.

La resiliencia (timeout + reintentos + circuit breaker) la aporta
``ResilientHttpClient``; ante timeout, 5xx o circuito abierto lanza
``DependenciaNoDisponible``, que ``CotizacionService`` traduce en fallback a
tarifa estándar (BITS-105 AC-2).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.domain import (
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    Hipoteca,
    NivelRiesgo,
    PerfilRiesgo,
)
from app.resilience import ResilientHttpClient

logger = logging.getLogger("cotizacion.adapters.perfilador")


class PerfiladorClient:
    def __init__(self, http: ResilientHttpClient) -> None:
        self._http = http

    async def aclose(self) -> None:
        await self._http.aclose()

    async def obtener_perfil(self, cliente_id: str) -> PerfilRiesgo | None:
        resp = await self._http.request("GET", f"/v1/perfiles/{cliente_id}")
        if resp.status_code == 404:
            logger.info("perfilamiento: perfil no calculado todavia cliente_id=%s", cliente_id)
            return None
        if resp.status_code != 200:
            logger.warning("perfilamiento respondio con error status_code=%s", resp.status_code)
            raise DependenciaNoDisponible(f"Perfilamiento respondió {resp.status_code}")
        perfil = perfil_desde_dict(resp.json())
        logger.info("perfilamiento resuelto nivel_riesgo=%s", perfil.nivel_riesgo)
        return perfil


def perfil_desde_dict(data: dict) -> PerfilRiesgo:
    """Parsea el ``PerfilRiesgo`` recibido de Perfilamiento — reusado tal
    cual por ``redis_cache.py`` para deserializar desde el caché, misma
    forma exacta de JSON."""
    return PerfilRiesgo(
        nivel_riesgo=NivelRiesgo(data["nivelRiesgo"]),
        factores=tuple(
            FactorRiesgo(
                descripcion=f["descripcion"],
                efecto=EfectoFactor(f["efecto"]),
                peso_relativo=(
                    Decimal(str(f["pesoRelativo"])) if f.get("pesoRelativo") is not None else None
                ),
            )
            for f in data.get("factores", [])
        ),
        factor_ajuste=Decimal(str(data["factorAjuste"])),
        fuentes_no_disponibles=tuple(data.get("fuentesNoDisponibles", [])),
        # Entradas del caché guardadas antes de BITS-101 no traen hipotecas: los datos del
        # crédito quedan DECLARADO, que es la dirección segura.
        hipotecas=tuple(
            Hipoteca(
                entidad_acreedora=h["entidadAcreedora"],
                valor_credito=Decimal(str(h["valorCredito"])),
                saldo_insoluto=Decimal(str(h["saldoInsoluto"])),
                plazo_restante_meses=int(h["plazoRestanteMeses"]),
            )
            for h in data.get("hipotecas", [])
        ),
    )


def perfil_a_dict(perfil: PerfilRiesgo) -> dict:
    """Inverso de ``perfil_desde_dict``: misma forma de JSON, para el caché y para guardar la
    foto del perfil dentro de la cotización."""
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
        "hipotecas": [
            {
                "entidadAcreedora": h.entidad_acreedora,
                "valorCredito": str(h.valor_credito),
                "saldoInsoluto": str(h.saldo_insoluto),
                "plazoRestanteMeses": h.plazo_restante_meses,
            }
            for h in perfil.hipotecas
        ],
    }
