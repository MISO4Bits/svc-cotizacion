"""Persistencia de la cotización activa sobre SQLite (aiosqlite).

Es el backend de desarrollo. Cuando se adopte Cloud Spanner (DI-009) se implementa el mismo
puerto con ese motor; el resto del servicio no cambia.

Una sola fila por cliente (``cliente_id`` es la llave): crear una cotización nueva reemplaza
la anterior. La fila guarda todo lo usado para calcular el precio, no solo el resultado.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

import aiosqlite

from app.adapters.perfilador_client import perfil_a_dict, perfil_desde_dict
from app.domain import (
    CoberturaPrecio,
    CodigoCobertura,
    Cotizacion,
    DatosCredito,
    Moneda,
    Oferta,
    OrigenDatos,
    RecursoNoEncontrado,
    Vigencia,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cotizacion_activa (
    cliente_id TEXT PRIMARY KEY,
    edad INTEGER NOT NULL,
    valor_credito TEXT NOT NULL,
    plazo_restante_meses INTEGER NOT NULL,
    entidad_acreedora TEXT NOT NULL,
    saldo_insoluto TEXT NOT NULL,
    origen_datos TEXT NOT NULL,
    tasa TEXT NOT NULL,
    version_tarifa INTEGER NOT NULL,
    prima_base TEXT NOT NULL,
    prima_mensual TEXT NOT NULL,
    suma_asegurada TEXT NOT NULL,
    cobertura_meses INTEGER NOT NULL,
    moneda TEXT NOT NULL,
    personalizado INTEGER NOT NULL,
    fuentes_no_disponibles TEXT NOT NULL,
    perfil TEXT,
    vigencia_desde TEXT NOT NULL,
    vigencia_hasta TEXT NOT NULL,
    creada_en TEXT NOT NULL,
    hogar TEXT
);
"""

# Tablas creadas antes de la cobertura de Hogar no tienen la columna ``hogar``.
_AGREGAR_HOGAR = "ALTER TABLE cotizacion_activa ADD COLUMN hogar TEXT"

_REEMPLAZAR = """
INSERT OR REPLACE INTO cotizacion_activa (
    cliente_id, edad, valor_credito, plazo_restante_meses, entidad_acreedora, saldo_insoluto,
    origen_datos, tasa, version_tarifa, prima_base, prima_mensual, suma_asegurada,
    cobertura_meses, moneda, personalizado, fuentes_no_disponibles, perfil,
    vigencia_desde, vigencia_hasta, creada_en, hogar
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SqliteDatabase:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with self.connect() as conn:
            await conn.executescript(_SCHEMA)
            columnas = {
                fila["name"]
                for fila in await conn.execute_fetchall("PRAGMA table_info(cotizacion_activa)")
            }
            if "hogar" not in columnas:
                await conn.execute(_AGREGAR_HOGAR)
            await conn.commit()

    @asynccontextmanager
    async def connect(self):
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()


class SqliteCotizacionRepository:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def reemplazar(self, cotizacion: Cotizacion) -> None:
        o = cotizacion.oferta
        d = cotizacion.datos_credito
        perfil = cotizacion.perfil_riesgo
        async with self._db.connect() as conn:
            await conn.execute(
                _REEMPLAZAR,
                (
                    cotizacion.cliente_id,
                    cotizacion.edad,
                    str(d.valor_credito),
                    d.plazo_restante_meses,
                    d.entidad_acreedora,
                    str(d.saldo_insoluto),
                    str(cotizacion.origen_datos),
                    str(cotizacion.tasa),
                    cotizacion.version_tarifa,
                    str(o.prima_base_mensual),
                    str(o.prima_mensual),
                    str(o.suma_asegurada),
                    o.cobertura_meses,
                    str(o.moneda),
                    int(o.personalizado),
                    json.dumps(list(o.fuentes_no_disponibles)),
                    json.dumps(perfil_a_dict(perfil)) if perfil is not None else None,
                    cotizacion.vigencia.desde.isoformat(),
                    cotizacion.vigencia.hasta.isoformat(),
                    cotizacion.creada_en.isoformat(),
                    _hogar_a_json(cotizacion.hogar),
                ),
            )
            await conn.commit()

    async def obtener_activa(self, cliente_id: str) -> Cotizacion:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM cotizacion_activa WHERE cliente_id = ?", (cliente_id,)
            )
            fila = await cursor.fetchone()
        if fila is None:
            raise RecursoNoEncontrado("el cliente no tiene una cotización activa")
        return _a_cotizacion(fila)

    async def eliminar_activa(self, cliente_id: str) -> None:
        async with self._db.connect() as conn:
            cursor = await conn.execute(
                "DELETE FROM cotizacion_activa WHERE cliente_id = ?", (cliente_id,)
            )
            await conn.commit()
            borradas = cursor.rowcount
        if borradas == 0:
            raise RecursoNoEncontrado("el cliente no tiene una cotización activa")


def _hogar_a_json(hogar: CoberturaPrecio | None) -> str | None:
    if hogar is None:
        return None
    return json.dumps(
        {
            "sumaAsegurada": str(hogar.suma_asegurada),
            "primaNeta": str(hogar.prima_neta),
            "iva": str(hogar.iva),
        }
    )


def _hogar_desde_json(crudo: str | None) -> CoberturaPrecio | None:
    if crudo is None:
        return None
    datos = json.loads(crudo)
    return CoberturaPrecio(
        codigo=CodigoCobertura.HOGAR,
        obligatoria=False,
        suma_asegurada=Decimal(datos["sumaAsegurada"]),
        prima_neta=Decimal(datos["primaNeta"]),
        iva=Decimal(datos["iva"]),
    )


def _a_cotizacion(fila: aiosqlite.Row) -> Cotizacion:
    oferta = Oferta(
        prima_mensual=Decimal(fila["prima_mensual"]),
        prima_base_mensual=Decimal(fila["prima_base"]),
        suma_asegurada=Decimal(fila["suma_asegurada"]),
        cobertura_meses=fila["cobertura_meses"],
        moneda=Moneda(fila["moneda"]),
        personalizado=bool(fila["personalizado"]),
        fuentes_no_disponibles=tuple(json.loads(fila["fuentes_no_disponibles"])),
    )
    return Cotizacion(
        cliente_id=fila["cliente_id"],
        edad=fila["edad"],
        datos_credito=DatosCredito(
            valor_credito=Decimal(fila["valor_credito"]),
            plazo_restante_meses=fila["plazo_restante_meses"],
            entidad_acreedora=fila["entidad_acreedora"],
            saldo_insoluto=Decimal(fila["saldo_insoluto"]),
        ),
        origen_datos=OrigenDatos(fila["origen_datos"]),
        tasa=Decimal(fila["tasa"]),
        version_tarifa=fila["version_tarifa"],
        oferta=oferta,
        perfil_riesgo=perfil_desde_dict(json.loads(fila["perfil"])) if fila["perfil"] else None,
        vigencia=Vigencia(
            datetime.fromisoformat(fila["vigencia_desde"]),
            datetime.fromisoformat(fila["vigencia_hasta"]),
        ),
        creada_en=datetime.fromisoformat(fila["creada_en"]),
        hogar=_hogar_desde_json(fila["hogar"]),
    )
