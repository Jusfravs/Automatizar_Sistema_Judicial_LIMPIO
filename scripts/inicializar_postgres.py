"""Crea la base, el rol de aplicacion y ejecuta migraciones versionadas."""

import argparse
import hashlib
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parents[1]
RUTA_MIGRACIONES = RAIZ / "migrations" / "postgres"


def obtener_config_postgres(dbname=None):
    password_app = os.getenv("POSTGRES_PASSWORD", "")
    password_admin = os.getenv("POSTGRES_ADMIN_PASSWORD", password_app)
    config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "admin_user": os.getenv("POSTGRES_ADMIN_USER", "postgres"),
        "admin_password": password_admin,
        "app_user": os.getenv("POSTGRES_USER", "judicial_app"),
        "app_password": password_app,
        "dbname": dbname or os.getenv("POSTGRES_DB", "casos_judiciales"),
        "sslmode": os.getenv("POSTGRES_SSLMODE"),
        "sslrootcert": os.getenv("POSTGRES_SSLROOTCERT"),
    }
    if not config["admin_password"]:
        raise RuntimeError("POSTGRES_ADMIN_PASSWORD_AUSENTE")
    if not config["app_password"]:
        raise RuntimeError("POSTGRES_PASSWORD_AUSENTE")
    return config


def crear_rol_y_base(config):
    conn = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        user=config["admin_user"],
        password=config["admin_password"],
        dbname="postgres",
        connect_timeout=10,
        **{k: config[k] for k in ("sslmode", "sslrootcert") if config.get(k)},
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (config["app_user"],))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(
                        sql.Identifier(config["app_user"])
                    ),
                    (config["app_password"],),
                )
                print("[OK] Rol de aplicacion creado.")
            else:
                print("[INFO] El rol de aplicacion ya existe; no se modifico su clave.")

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config["dbname"],))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                        sql.Identifier(config["dbname"]),
                        sql.Identifier(config["app_user"]),
                    )
                )
                print("[OK] Base de datos creada: %s" % config["dbname"])
            else:
                cur.execute(
                    sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                        sql.Identifier(config["dbname"]),
                        sql.Identifier(config["app_user"]),
                    )
                )
                print("[INFO] Base existente verificada: %s" % config["dbname"])
    finally:
        conn.close()


def ejecutar_migraciones(config):
    archivos = sorted(RUTA_MIGRACIONES.glob("*.sql"))
    if not archivos:
        raise RuntimeError("MIGRACIONES_POSTGRES_AUSENTES")
    conn = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        user=config["admin_user"],
        password=config["admin_password"],
        dbname=config["dbname"],
        connect_timeout=10,
        **{k: config[k] for k in ("sslmode", "sslrootcert") if config.get(k)},
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    checksum CHAR(64) NOT NULL,
                    aplicada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            for archivo in archivos:
                contenido = archivo.read_text(encoding="utf-8")
                checksum = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
                cur.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = %s",
                    (archivo.name,),
                )
                existente = cur.fetchone()
                if existente:
                    if existente[0] != checksum:
                        raise RuntimeError(
                            "MIGRACION_MODIFICADA_DESPUES_DE_APLICAR:%s" % archivo.name
                        )
                    print("[INFO] Migracion ya aplicada: %s" % archivo.name)
                    continue
                try:
                    cur.execute(contenido)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (archivo.name, checksum),
                    )
                    conn.commit()
                    print("[OK] Migracion aplicada: %s" % archivo.name)
                except Exception:
                    conn.rollback()
                    raise

            cur.execute(
                sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                    sql.Identifier(config["app_user"])
                )
            )
            cur.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}").format(
                    sql.Identifier(config["app_user"])
                )
            )
            cur.execute(
                sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                    sql.Identifier(config["app_user"])
                )
            )
            conn.commit()
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dbname", default=None)
    args = parser.parse_args(argv)
    config = obtener_config_postgres(args.dbname)
    crear_rol_y_base(config)
    ejecutar_migraciones(config)
    print("[OK] PostgreSQL listo para el Sistema Judicial.")


if __name__ == "__main__":
    main()
