"""Indexa el texto de las actuaciones del respaldo histórico en un SQLite local.

La migración del 2 de octubre dejó vacío el ``detalle`` de las actuaciones
históricas en PostgreSQL; el texto íntegro quedó en los segmentos
``historico-NN.jsonl.gz`` (una fila por línea: ``tabla<TAB>json``). Este índice
permite leerlo por causa sin descargar nada. Guárdelo junto al respaldo: tiene
el mismo contenido judicial y la misma protección.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
from pathlib import Path


def indexar(respaldo: Path, destino: Path) -> dict:
    manifiesto = json.loads((respaldo / "manifest.json").read_text(encoding="utf-8"))
    if destino.exists():
        destino.unlink()
    db = sqlite3.connect(destino)
    db.execute("""
        CREATE TABLE actuaciones (
            actuacion_id TEXT PRIMARY KEY, numero_causa TEXT NOT NULL,
            fecha TEXT, titulo TEXT, detalle TEXT, carpeta TEXT
        )
    """)
    filas = 0
    for segmento in sorted(respaldo.glob("historico-*.jsonl.gz")):
        lote = []
        with gzip.open(segmento, "rt", encoding="utf-8") as origen:
            for linea in origen:
                tabla, datos = linea.split("\t", 1)
                if tabla != "actuaciones_procesales":
                    continue
                fila = json.loads(datos)
                lote.append((
                    fila["actuacion_id"], fila["numero_causa"], fila.get("fecha"),
                    fila.get("titulo") or "", fila.get("detalle") or "", fila.get("carpeta") or "",
                ))
        db.executemany("INSERT OR REPLACE INTO actuaciones VALUES (?, ?, ?, ?, ?, ?)", lote)
        db.commit()
        filas += len(lote)
    db.execute("CREATE INDEX idx_actuaciones_causa ON actuaciones(numero_causa, fecha)")
    db.commit()
    db.close()
    esperadas = (manifiesto.get("tablas") or {}).get("actuaciones_procesales")
    if esperadas is not None and filas != esperadas:
        raise RuntimeError(f"INDICE_INCOMPLETO: {filas} de {esperadas} filas")
    return {"filas": filas, "esperadas": esperadas}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("respaldo", type=Path, help="Carpeta del respaldo con manifest.json")
    parser.add_argument("--destino", type=Path,
                        help="SQLite de salida; por defecto, dentro del respaldo")
    args = parser.parse_args()
    destino = args.destino or args.respaldo / "indice_actuaciones.sqlite"
    print(json.dumps(indexar(args.respaldo, destino)))


if __name__ == "__main__":
    main()
