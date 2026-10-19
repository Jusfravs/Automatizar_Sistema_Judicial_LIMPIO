"""Recalcula la condición de las causas ya guardadas sin reconsultar SATJE.

Usa el mismo historial que vio el motor (``datos_json``) y solo escribe la
condición: columnas ``condicion``, ``fecha_condicion`` y ``actuacion_condicion``
y las mismas claves dentro de ``datos_json.datos`` (para el Excel). La etapa y
la fase no se tocan. Sin ``--aplicar`` solo informa cuántas cambiarían.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from psycopg2.extras import Json

from src.agente_extractor import MotorInferenciaProcesal
from src.repositorio_postgres import RepositorioColaPostgres


def _historial_guardado(conn, numero_causa: str) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT fecha, titulo, detalle, carpeta FROM actuaciones_procesales
            WHERE numero_causa = %s ORDER BY fecha, actuacion_id
        """, (numero_causa,))
        return [
            {"fecha": f, "titulo": t, "detalle": d or t, "ORIGEN_CARPETA": c}
            for f, t, d, c in cursor.fetchall()
        ]


def _condicion(conn, numero_causa: str, payload) -> dict | None:
    datos = {}
    if isinstance(payload, dict):
        datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
    # El historial del lote queda en datos_json solo en algunas causas; el
    # resto se lee del historial append-only.
    actuaciones = datos.get("HISTORIAL_ACTUACIONES") or _historial_guardado(conn, numero_causa)
    if not actuaciones:
        return None
    resultado = MotorInferenciaProcesal.inferir_estado_procesal(
        actuaciones, causa=numero_causa
    )
    if not resultado or not resultado.get("ULTIMA_ETAPA"):
        return None
    return {
        "CONDICION": resultado.get("CONDICION") or "VIGENTE",
        "FECHA CONDICION": resultado.get("FECHA_CONDICION"),
        "ACTUACION CONDICION": resultado.get("ACTUACION_CONDICION"),
    }


def recalcular(config_path: Path, aplicar: bool = False, limite: int = 0) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    resumen = Counter()
    conn = repo._get_connection()
    if not aplicar:
        conn.set_session(readonly=True)
    ultima_causa = ""
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'expedientes' AND column_name = 'condicion'
            """)
            con_columna = cursor.fetchone() is not None
        if aplicar and not con_columna:
            raise RuntimeError("FALTA_MIGRACION_005_CONDICION")
        # En seco y antes de la migración, todas cuentan como VIGENTE.
        columna = "condicion" if con_columna else "'VIGENTE'"
        while True:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    SELECT numero_causa, datos_json, {columna} FROM expedientes
                    WHERE numero_causa > %s ORDER BY numero_causa LIMIT 50
                """, (ultima_causa,))
                filas = cursor.fetchall()
            if not filas:
                break
            for numero_causa, payload, condicion_actual in filas:
                ultima_causa = numero_causa
                resumen["vistas"] += 1
                nueva = _condicion(conn, numero_causa, payload)
                if nueva is None:
                    resumen["sin_historial"] += 1
                    continue
                resumen[nueva["CONDICION"]] += 1
                if nueva["CONDICION"] == condicion_actual:
                    continue
                resumen["cambian"] += 1
                if not aplicar:
                    continue
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE expedientes SET
                            condicion = %s, fecha_condicion = %s, actuacion_condicion = %s,
                            datos_json = CASE
                                WHEN jsonb_typeof(datos_json -> 'datos') = 'object'
                                THEN jsonb_set(datos_json, '{datos}', (datos_json -> 'datos') || %s)
                                ELSE datos_json
                            END
                        WHERE numero_causa = %s
                    """, (
                        nueva["CONDICION"],
                        str(nueva["FECHA CONDICION"]) if nueva["FECHA CONDICION"] else None,
                        nueva["ACTUACION CONDICION"],
                        Json(nueva), numero_causa,
                    ))
            if aplicar:
                conn.commit()
            if limite and resumen["vistas"] >= limite:
                break
    finally:
        conn.close()
    return dict(resumen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config_supabase.json", type=Path)
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe los cambios; sin esta opción solo informa")
    parser.add_argument("--limite", type=int, default=0,
                        help="Máximo de causas a revisar; 0 revisa todas")
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    print(json.dumps(recalcular(args.config, args.aplicar, args.limite), ensure_ascii=False))


if __name__ == "__main__":
    main()
