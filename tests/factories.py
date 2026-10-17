"""Constructores de objetos de dominio para las pruebas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain import (
    Cotizacion,
    DatosCredito,
    EfectoFactor,
    FactorRiesgo,
    Moneda,
    NivelRiesgo,
    Oferta,
    OrigenDatos,
    PerfilRiesgo,
    SolicitudCotizacion,
    Vigencia,
)


def datos_credito(
    saldo: str = "140000000", plazo: int = 240, entidad: str = "Banco X"
) -> DatosCredito:
    return DatosCredito(
        valor_credito=Decimal("150000000"),
        plazo_restante_meses=plazo,
        entidad_acreedora=entidad,
        saldo_insoluto=Decimal(saldo),
    )


def solicitud(
    *, cliente_id: str = "cli-1", edad: int = 38, saldo: str = "140000000", plazo: int = 240
) -> SolicitudCotizacion:
    return SolicitudCotizacion(
        cliente_id=cliente_id, edad=edad, datos_credito=datos_credito(saldo=saldo, plazo=plazo)
    )


def perfil(factor: str = "0.90", *, fuentes_no_disponibles: tuple[str, ...] = ()) -> PerfilRiesgo:
    return PerfilRiesgo(
        nivel_riesgo=NivelRiesgo.BAJO,
        factores=(
            FactorRiesgo("Historial de pagos excelente", EfectoFactor.POSITIVO, Decimal("0.1")),
        ),
        factor_ajuste=Decimal(factor),
        fuentes_no_disponibles=fuentes_no_disponibles,
    )


def cotizacion(
    *, cliente_id: str = "cli-1", personalizado: bool = False, creada_en: datetime | None = None
) -> Cotizacion:
    ahora = creada_en or datetime.now(UTC)
    prima_base = Decimal("60000")
    prima = Decimal("54000") if personalizado else prima_base
    return Cotizacion(
        cliente_id=cliente_id,
        edad=38,
        datos_credito=datos_credito(),
        origen_datos=OrigenDatos.DECLARADO,
        tasa=Decimal("0.196"),
        version_tarifa=1,
        oferta=Oferta(
            prima_mensual=prima,
            prima_base_mensual=prima_base,
            suma_asegurada=Decimal("140000000"),
            cobertura_meses=240,
            moneda=Moneda.COP,
            personalizado=personalizado,
            fuentes_no_disponibles=() if personalizado else ("perfilamiento",),
        ),
        perfil_riesgo=perfil() if personalizado else None,
        vigencia=Vigencia(ahora, ahora + timedelta(days=30)),
        creada_en=ahora,
    )
