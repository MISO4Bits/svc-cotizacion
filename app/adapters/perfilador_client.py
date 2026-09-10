"""Adaptador HTTP hacia el servicio de Perfilamiento (implementa PerfilRiesgoPort).

El contrato con Perfilamiento no está definido en Jira (queda como propuesta del
equipo). Para el experimento:

  POST {base}/perfiles
  body: { clienteId, datosCredito{...}, cuestionarioHabitos{...} }
  200:  { nivelRiesgo, factorAjuste, factores[], fuentesNoDisponibles[] }

La resiliencia (timeout 700 ms + reintentos + circuit breaker) la aporta
``ResilientHttpClient``; ante timeout, 5xx o circuito abierto lanza
``DependenciaNoDisponible``, que ``CotizacionService`` traduce en fallback a
tarifa estándar (BITS-105 AC-2).
"""

from __future__ import annotations

from decimal import Decimal

from app.domain import (
    DependenciaNoDisponible,
    EfectoFactor,
    FactorRiesgo,
    NivelRiesgo,
    PerfilRiesgo,
    SolicitudCotizacion,
)
from app.resilience import ResilientHttpClient


class PerfiladorClient:
    def __init__(self, http: ResilientHttpClient) -> None:
        self._http = http

    async def aclose(self) -> None:
        await self._http.aclose()

    async def perfilar(self, solicitud: SolicitudCotizacion) -> PerfilRiesgo:
        dc = solicitud.datos_credito
        q = solicitud.cuestionario_habitos
        cuerpo = {
            "clienteId": solicitud.cliente_id,
            "datosCredito": {
                "valorCredito": float(dc.valor_credito),
                "plazoMeses": dc.plazo_meses,
                "edad": dc.edad,
                "saldoInsoluto": float(dc.saldo_insoluto),
            },
            "cuestionarioHabitos": {
                "consumeTabaco": q.consume_tabaco,
                "actividadFisica": str(q.actividad_fisica),
                "condicionesPreexistentes": q.condiciones_preexistentes,
                "dependientesEconomicos": q.dependientes_economicos,
            },
        }

        resp = await self._http.request("POST", "/perfiles", json=cuerpo)
        if resp.status_code != 200:
            raise DependenciaNoDisponible(f"Perfilamiento respondió {resp.status_code}")
        return _a_perfil(resp.json())


def _a_perfil(data: dict) -> PerfilRiesgo:
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
    )
