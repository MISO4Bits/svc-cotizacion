"""Fábrica de adaptadores del servicio de Cotización (sin framework de DI)."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.fakes import FakeCotizacionRepository, FakeProveedorTarifa
from app.config import Settings
from app.ports import CotizacionRepositoryPort, ProveedorTarifaPort


@dataclass
class Dependencias:
    proveedor: ProveedorTarifaPort
    repositorio: CotizacionRepositoryPort

    async def aclose(self) -> None:
        for adaptador in (self.proveedor, self.repositorio):
            cerrar = getattr(adaptador, "aclose", None)
            if cerrar is not None:
                await cerrar()


def build_dependencias(settings: Settings) -> Dependencias:
    if settings.adapters == "fake":
        return Dependencias(
            proveedor=FakeProveedorTarifa(),
            repositorio=FakeCotizacionRepository(),
        )
    raise ValueError(f"adapters no soportado: {settings.adapters}")
