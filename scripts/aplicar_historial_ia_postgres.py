"""Aplica la migración aditiva 002 con el usuario de aplicación PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.repositorio_postgres import RepositorioColaPostgres


RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "postgres" / "002_historial_inferencia_ia.sql"


def aplicar(config_path: Path) -> str:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    contenido = MIGRACION.read_text(encoding="utf-8")
    checksum = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    conn = repo._get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT checksum FROM schema_migrations WHERE version=%s",
                    (MIGRACION.name,),
                )
                existente = cursor.fetchone()
                if existente:
                    if existente[0] != checksum:
                        raise RuntimeError("MIGRACION_002_MODIFICADA")
                    return "ya_aplicada"
                cursor.execute(contenido)
                cursor.execute(
                    "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                    (MIGRACION.name, checksum),
                )
        return "aplicada"
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    args = parser.parse_args()
    print(json.dumps({"migracion": MIGRACION.name,
                      "estado": aplicar(args.config.resolve())}))


if __name__ == "__main__":
    main()
