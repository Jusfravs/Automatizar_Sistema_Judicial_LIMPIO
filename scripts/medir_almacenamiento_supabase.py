"""Mide el tamaño de PostgreSQL y Storage sin leer contenido de expedientes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.repositorio_postgres import RepositorioColaPostgres


LIMITE_DB = 500_000_000
LIMITE_STORAGE = 1_000_000_000


def main() -> None:
    ruta_config = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config_supabase.json")
    config = json.loads(ruta_config.read_text(encoding="utf-8-sig"))
    repo = RepositorioColaPostgres.desde_config(config["base_de_datos"])
    with repo._connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            db_bytes = int(cursor.fetchone()[0])
            cursor.execute("""
                SELECT bucket_id, count(*),
                       COALESCE(sum((metadata->>'size')::bigint), 0)
                FROM storage.objects
                GROUP BY bucket_id ORDER BY bucket_id
            """)
            buckets = [
                {"bucket": nombre, "objetos": cantidad, "bytes": int(tamano)}
                for nombre, cantidad, tamano in cursor.fetchall()
            ]
    storage_bytes = sum(item["bytes"] for item in buckets)
    print(json.dumps({
        "postgres": {"bytes": db_bytes, "limite_gratis": LIMITE_DB,
                     "porcentaje": round(db_bytes / LIMITE_DB * 100, 1)},
        "storage": {"bytes": storage_bytes, "limite_gratis": LIMITE_STORAGE,
                    "porcentaje": round(storage_bytes / LIMITE_STORAGE * 100, 1),
                    "buckets": buckets},
        "alerta": db_bytes >= LIMITE_DB * .75 or storage_bytes >= LIMITE_STORAGE * .75,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
