"""Persistencia SQLite de la cotización activa: una fila por cliente."""

from __future__ import annotations

import pytest

from app.adapters.sqlite import SqliteCotizacionRepository, SqliteDatabase
from app.domain import RecursoNoEncontrado
from tests.factories import cotizacion


@pytest.fixture
async def repo(tmp_path):
    db = SqliteDatabase(str(tmp_path / "cotizaciones.db"))
    await db.init()
    return SqliteCotizacionRepository(db)


async def test_guarda_y_recupera_la_cotizacion_con_todos_sus_insumos(repo):
    original = cotizacion(personalizado=True)

    await repo.reemplazar(original)

    assert await repo.obtener_activa("cli-1") == original


async def test_guarda_y_recupera_la_cotizacion_sin_perfil(repo):
    original = cotizacion(personalizado=False)

    await repo.reemplazar(original)

    recuperada = await repo.obtener_activa("cli-1")
    assert recuperada == original
    assert recuperada.perfil_riesgo is None
    assert recuperada.oferta.fuentes_no_disponibles == ("perfilamiento",)


async def test_una_cotizacion_nueva_reemplaza_a_la_anterior_y_no_se_acumulan(repo, tmp_path):
    await repo.reemplazar(cotizacion(personalizado=False))
    await repo.reemplazar(cotizacion(personalizado=True))

    assert (await repo.obtener_activa("cli-1")).oferta.personalizado is True
    async with repo._db.connect() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM cotizacion_activa")
        assert (await cursor.fetchone())[0] == 1


async def test_cada_cliente_tiene_la_suya(repo):
    await repo.reemplazar(cotizacion(cliente_id="cli-1", personalizado=False))
    await repo.reemplazar(cotizacion(cliente_id="cli-2", personalizado=True))

    assert (await repo.obtener_activa("cli-1")).oferta.personalizado is False
    assert (await repo.obtener_activa("cli-2")).oferta.personalizado is True


async def test_cliente_sin_cotizacion_no_se_encuentra(repo):
    with pytest.raises(RecursoNoEncontrado):
        await repo.obtener_activa("nadie")


async def test_eliminar_borra_la_fila_del_cliente_y_no_la_de_otros(repo):
    await repo.reemplazar(cotizacion(cliente_id="cli-1"))
    await repo.reemplazar(cotizacion(cliente_id="cli-2"))

    await repo.eliminar_activa("cli-1")

    with pytest.raises(RecursoNoEncontrado):
        await repo.obtener_activa("cli-1")
    assert (await repo.obtener_activa("cli-2")).cliente_id == "cli-2"


async def test_eliminar_de_un_cliente_sin_cotizacion_no_se_encuentra(repo):
    with pytest.raises(RecursoNoEncontrado):
        await repo.eliminar_activa("nadie")


async def test_la_cotizacion_sobrevive_a_un_reinicio_del_servicio(tmp_path):
    ruta = str(tmp_path / "pod.db")
    db = SqliteDatabase(ruta)
    await db.init()
    await SqliteCotizacionRepository(db).reemplazar(cotizacion())

    otro_arranque = SqliteDatabase(ruta)
    await otro_arranque.init()  # CREATE TABLE IF NOT EXISTS: no borra nada

    assert (await SqliteCotizacionRepository(otro_arranque).obtener_activa("cli-1")).edad == 38


async def test_guarda_y_recupera_la_cobertura_de_hogar(repo):
    original = cotizacion(personalizado=True)

    await repo.reemplazar(original)

    recuperada = await repo.obtener_activa("cli-1")
    assert recuperada.hogar == original.hogar
    assert recuperada.hogar.prima_total == 17672


async def test_una_tabla_anterior_a_hogar_se_migra_y_sus_filas_quedan_sin_hogar(tmp_path):
    import aiosqlite

    ruta = str(tmp_path / "vieja.db")
    async with aiosqlite.connect(ruta) as conn:
        await conn.execute("CREATE TABLE cotizacion_activa (cliente_id TEXT PRIMARY KEY)")
        await conn.commit()
    db = SqliteDatabase(ruta)

    await db.init()
    await db.init()  # idempotente: la columna ya existe

    async with db.connect() as conn:
        columnas = {
            f["name"] for f in await conn.execute_fetchall("PRAGMA table_info(cotizacion_activa)")
        }
    assert "hogar" in columnas


async def test_una_cotizacion_sin_hogar_se_recupera_sin_hogar(repo):
    await repo.reemplazar(cotizacion(sin_hogar=True))

    assert (await repo.obtener_activa("cli-1")).hogar is None


async def test_la_foto_del_perfil_no_guarda_las_hipotecas(repo):
    from dataclasses import replace
    from decimal import Decimal

    from app.domain import Hipoteca

    hipoteca = Hipoteca("BBVA COLOMBIA S.A.", Decimal("150000000"), Decimal("140000000"), 240)
    original = cotizacion(personalizado=True)
    con_hipotecas = replace(
        original, perfil_riesgo=replace(original.perfil_riesgo, hipotecas=(hipoteca,))
    )

    await repo.reemplazar(con_hipotecas)

    assert (await repo.obtener_activa("cli-1")).perfil_riesgo.hipotecas == ()
