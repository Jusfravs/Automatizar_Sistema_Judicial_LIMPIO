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
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# Permite ejecutarlo como `python scripts/recalcular_condicion.py` desde la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from psycopg2.extras import Json

from src.agente_extractor import MotorInferenciaProcesal
from src.repositorio_postgres import RepositorioColaPostgres


def _historial_guardado(conn, numero_causa: str, respaldo=None, resumen=None) -> list[dict]:
    """Historial de PostgreSQL; el texto vaciado se completa desde el respaldo."""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT actuacion_id, fecha, titulo, detalle, carpeta FROM actuaciones_procesales
            WHERE numero_causa = %s ORDER BY fecha, actuacion_id
        """, (numero_causa,))
        filas = cursor.fetchall()
    textos = {}
    if respaldo is not None and filas:
        textos = {
            act_id: (t, d) for act_id, t, d in respaldo.execute(
                "SELECT actuacion_id, titulo, detalle FROM actuaciones WHERE numero_causa = ?",
                (numero_causa,),
            )
        }
    historial = []
    for act_id, fecha, titulo, detalle, carpeta in filas:
        if resumen is not None and not detalle:
            # Fila compactada: se cuenta si el respaldo trae su texto.
            resumen["filas_sin_detalle"] += 1
            if act_id in textos:
                resumen["filas_emparejadas"] += 1
        titulo_r, detalle_r = textos.get(act_id, ("", ""))
        titulo = titulo or titulo_r
        detalle = detalle or detalle_r
        historial.append({
            "fecha": fecha, "titulo": titulo, "detalle": detalle or titulo,
            "ORIGEN_CARPETA": carpeta,
        })
    return historial


def _condicion(conn, numero_causa: str, payload, resumen: Counter, respaldo=None) -> dict | None:
    datos = {}
    if isinstance(payload, dict):
        datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
    # El historial del lote queda en datos_json solo en algunas causas; el
    # resto se lee del historial append-only (compactado: sin detalle).
    actuaciones = (datos.get("HISTORIAL_ACTUACIONES")
                   or _historial_guardado(conn, numero_causa, respaldo, resumen))
    if not actuaciones:
        return None
    # Cobertura: alguna actuación trae detalle además del rótulo. No acredita
    # que haya una decisión legible: eso lo decide el motor (POR_CONFIRMAR).
    if any(str(a.get("detalle") or "").strip() not in ("", str(a.get("titulo") or "").strip())
           for a in actuaciones):
        resumen["con_detalle"] += 1
    else:
        resumen["solo_rotulos"] += 1
    if any(not str(a.get("titulo") or "").strip() and not str(a.get("detalle") or "").strip()
           for a in actuaciones):
        resumen["con_filas_vacias"] += 1
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


def _procesar_lote(repo, aplicar, columna, desde, tamano, resumen, respaldo=None) -> str | None:
    """Procesa hasta `tamano` causas tras `desde` en una conexión propia.

    Devuelve la última causa vista, o None si no quedan. Una conexión por
    lote: un corte de red o una suspensión del equipo solo repite ese lote.
    """
    conn = repo._get_connection()
    try:
        if not aplicar:
            conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT numero_causa, datos_json, {columna}, version_fuente_en FROM expedientes
                WHERE numero_causa > %s ORDER BY numero_causa LIMIT %s
            """, (desde, tamano))
            filas = cursor.fetchall()
        if not filas:
            return None
        parcial = Counter()
        for numero_causa, payload, condicion_actual, version in filas:
            parcial["vistas"] += 1
            nueva = _condicion(conn, numero_causa, payload, parcial, respaldo)
            if nueva is None:
                parcial["sin_historial"] += 1
                continue
            parcial[nueva["CONDICION"]] += 1
            if nueva["CONDICION"] == condicion_actual:
                continue
            parcial["cambian"] += 1
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
                    WHERE numero_causa = %s AND version_fuente_en IS NOT DISTINCT FROM %s
                """, (
                    nueva["CONDICION"],
                    str(nueva["FECHA CONDICION"]) if nueva["FECHA CONDICION"] else None,
                    nueva["ACTUACION CONDICION"],
                    Json(nueva), numero_causa, version,
                ))
                # Un lote la actualizó entre la lectura y la escritura: manda
                # el resultado nuevo, que ya trae su propia condición.
                if cursor.rowcount == 0:
                    parcial["omitidas_por_cambio"] += 1
        if aplicar:
            conn.commit()
        # Solo se suma al resumen cuando el lote terminó (y se confirmó).
        resumen.update(parcial)
        return filas[-1][0]
    finally:
        conn.close()


def recalcular(config_path: Path, aplicar: bool = False, limite: int = 0,
               desde: str = "", intentos: int = 5, ruta_respaldo: Path | None = None) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    # Solo lectura: el índice nunca se modifica desde aquí.
    respaldo = (
        sqlite3.connect(f"file:{ruta_respaldo.as_posix()}?mode=ro", uri=True)
        if ruta_respaldo else None
    )
    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    resumen = Counter()
    conn = repo._get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'expedientes' AND column_name = 'condicion'
            """)
            con_columna = cursor.fetchone() is not None
    finally:
        conn.close()
    if aplicar and not con_columna:
        raise RuntimeError("FALTA_MIGRACION_005_CONDICION")
    if aplicar and respaldo is None:
        # Sin el texto compactado casi todo el histórico quedaría POR_CONFIRMAR.
        raise RuntimeError("FALTA_RESPALDO: use --respaldo para --aplicar")
    # En seco y antes de la migración, todas cuentan como VIGENTE.
    columna = "condicion" if con_columna else "'VIGENTE'"
    ultima_causa = desde
    fallos = 0
    while not (limite and resumen["vistas"] >= limite):
        tamano = min(50, limite - resumen["vistas"]) if limite else 50
        try:
            siguiente = _procesar_lote(
                repo, aplicar, columna, ultima_causa, tamano, resumen, respaldo
            )
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            fallos += 1
            if fallos > intentos:
                print(f"Interrumpido tras {ultima_causa!r}; reanudar con --desde", file=sys.stderr)
                raise
            time.sleep(min(60, 5 * fallos))
            continue
        fallos = 0
        if siguiente is None:
            break
        ultima_causa = siguiente
        print(f"... {resumen['vistas']} causas (hasta {ultima_causa})", file=sys.stderr, flush=True)
    if respaldo is not None:
        respaldo.close()
    if resumen["filas_sin_detalle"]:
        resumen["cobertura_respaldo_pct"] = round(
            100 * resumen["filas_emparejadas"] / resumen["filas_sin_detalle"], 2
        )
    return dict(resumen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config_supabase.json", type=Path)
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe los cambios; sin esta opción solo informa")
    parser.add_argument("--limite", type=int, default=0,
                        help="Máximo de causas a revisar; 0 revisa todas")
    parser.add_argument("--desde", default="",
                        help="Reanuda después de este número de causa")
    parser.add_argument("--respaldo", type=Path,
                        help="indice_actuaciones.sqlite (scripts/indexar_respaldo_historico.py) "
                             "para leer el texto que la compactación vació")
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    print(json.dumps(recalcular(args.config, args.aplicar, args.limite, args.desde,
                                ruta_respaldo=args.respaldo),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
