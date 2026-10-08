"""Migraciones del esquema para bases creadas antes de los centros de formación.

`create_all` crea las tablas nuevas pero no altera las existentes. Esta migración es idempotente:
agrega `centro_id` a lotes, usuarios y actividad, crea el centro por defecto y le asigna todos los
datos existentes, y cambia la unicidad de los lotes (número y abreviatura) para que sea por centro.
Funciona en SQLite (desarrollo) y MariaDB/MySQL (producción).
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from .models import Lote

log = logging.getLogger("migraciones")


def _columnas(conn: Connection, tabla: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(tabla)}


def _centro_defecto(conn: Connection, codigo: str, nombre: str, regional: str) -> int:
    cid = conn.execute(text("SELECT id FROM centros ORDER BY id LIMIT 1")).scalar()
    if cid is None:
        conn.execute(text("INSERT INTO centros (codigo, nombre, regional, activo) VALUES (:c, :n, :r, :a)"),
                     {"c": codigo, "n": nombre, "r": regional, "a": True})
        cid = conn.execute(text("SELECT id FROM centros ORDER BY id LIMIT 1")).scalar()
    return cid


def _reconstruir_lotes_sqlite(conn: Connection, centro_id: int) -> None:
    """SQLite no permite quitar restricciones UNIQUE: se recrea la tabla (procedimiento oficial de SQLite)."""
    conn.exec_driver_sql("DROP TABLE IF EXISTS _lotes_nueva")  # resto de un intento fallido
    ddl = str(CreateTable(Lote.__table__).compile(conn)).replace("CREATE TABLE lotes", "CREATE TABLE _lotes_nueva", 1)
    conn.exec_driver_sql(ddl)
    conn.exec_driver_sql(
        "INSERT INTO _lotes_nueva (id, centro_id, numero, nombre, abreviatura, color, activo) "
        f"SELECT id, {int(centro_id)}, numero, nombre, abreviatura, color, activo FROM lotes")
    conn.exec_driver_sql("DROP TABLE lotes")
    conn.exec_driver_sql("ALTER TABLE _lotes_nueva RENAME TO lotes")
    for idx in Lote.__table__.indexes:
        conn.execute(CreateIndex(idx))


def _lotes_mysql(conn: Connection, centro_id: int) -> None:
    conn.exec_driver_sql("ALTER TABLE lotes ADD COLUMN centro_id INTEGER NULL")
    conn.execute(text("UPDATE lotes SET centro_id = :c"), {"c": centro_id})
    conn.exec_driver_sql("ALTER TABLE lotes MODIFY centro_id INTEGER NOT NULL")
    for uc in inspect(conn).get_unique_constraints("lotes"):
        if uc["column_names"] in (["numero"], ["abreviatura"]):
            conn.exec_driver_sql(f"ALTER TABLE lotes DROP INDEX `{uc['name']}`")
    conn.exec_driver_sql("ALTER TABLE lotes ADD CONSTRAINT uq_lote_centro_numero UNIQUE (centro_id, numero)")
    conn.exec_driver_sql("ALTER TABLE lotes ADD CONSTRAINT uq_lote_centro_abrev UNIQUE (centro_id, abreviatura)")
    conn.exec_driver_sql("ALTER TABLE lotes ADD CONSTRAINT fk_lotes_centro FOREIGN KEY (centro_id) REFERENCES centros (id)")


def _agregar_columna(conn: Connection, tabla: str, mysql: bool) -> None:
    if mysql:
        conn.exec_driver_sql(f"ALTER TABLE {tabla} ADD COLUMN centro_id INTEGER NULL")
        conn.exec_driver_sql(f"ALTER TABLE {tabla} ADD CONSTRAINT fk_{tabla}_centro "
                             f"FOREIGN KEY (centro_id) REFERENCES centros (id)")
    else:
        conn.exec_driver_sql(f"ALTER TABLE {tabla} ADD COLUMN centro_id INTEGER REFERENCES centros (id)")
    conn.exec_driver_sql(f"CREATE INDEX ix_{tabla}_centro_id ON {tabla} (centro_id)")


def migrar_centros(engine: Engine, codigo: str, nombre: str, regional: str) -> bool:
    """Devuelve True si migró algo. Debe llamarse después de `create_all` (la tabla centros ya existe)."""
    with engine.connect() as conn:
        tablas = set(inspect(conn).get_table_names())
        if "lotes" not in tablas or "centro_id" in _columnas(conn, "lotes"):
            return False
    mysql = engine.dialect.name in ("mysql", "mariadb")
    log.warning("Migrando la base de datos a centros de formación (centro por defecto: %s)", nombre)
    with engine.connect() as conn:
        if not mysql:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")  # debe ejecutarse fuera de una transacción
            conn.commit()
        with conn.begin():
            cid = _centro_defecto(conn, codigo, nombre, regional)
            if mysql:
                _lotes_mysql(conn, cid)
            else:
                _reconstruir_lotes_sqlite(conn, cid)
            for tabla in ("usuarios", "actividad"):
                if "centro_id" not in _columnas(conn, tabla):
                    _agregar_columna(conn, tabla, mysql)
            # Los usuarios existentes (administradores y líderes) quedan en el centro por defecto
            conn.execute(text("UPDATE usuarios SET centro_id = :c WHERE centro_id IS NULL AND rol <> 'MANAGER'"),
                         {"c": cid})
            conn.execute(text("UPDATE actividad SET centro_id = :c WHERE centro_id IS NULL"), {"c": cid})
            if not mysql:
                rotas = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if rotas:
                    raise RuntimeError(f"La migración dejó referencias inválidas: {rotas[:5]}")
        if not mysql:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()
    engine.dispose()  # ninguna conexión del pool conserva el estado de la migración
    return True

