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
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# Permite ejecutarlo como `python scripts/recalcular_condicion.py` desde la raíz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from psycopg2.extras import Json

from src.agente_extractor import (
    MotorInferenciaProcesal, _decodificar_entidades_satje, normalizar_texto,
)
from src.repositorio_postgres import RepositorioColaPostgres


def _historiales_del_lote(conn, causas: list[str]) -> dict[str, list[tuple]]:
    """Actuaciones de PostgreSQL de varias causas en una sola consulta."""
    por_causa: dict[str, list[tuple]] = {c: [] for c in causas}
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT numero_causa, actuacion_id, fecha, titulo, detalle, carpeta
            FROM actuaciones_procesales
            WHERE numero_causa = ANY(%s) ORDER BY numero_causa, fecha, actuacion_id
        """, (causas,))
        for numero_causa, *fila in cursor.fetchall():
            por_causa[numero_causa].append(tuple(fila))
    return por_causa


def _historial_guardado(filas: list[tuple], numero_causa: str, respaldo=None,
                        resumen=None) -> list[dict]:
    """Historial de PostgreSQL; el texto vaciado se completa desde el respaldo."""
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
        titulo = _texto_plano(titulo or titulo_r)
        detalle = _texto_plano(detalle or detalle_r)
        # Un "título" que es el inicio de un HTML ("<p style=...VI") no es rótulo.
        if str(titulo_r or "").lstrip().startswith("<") and titulo == detalle[:len(titulo)]:
            titulo = ""
        historial.append({
            "fecha": _fecha_dia(fecha), "titulo": titulo, "detalle": detalle or titulo,
            "ORIGEN_CARPETA": carpeta,
        })
    return _unir_cuerpos(historial)


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _fecha_dia(fecha):
    """El respaldo trae fechas ISO con hora; el motor ordena por día (dd/mm/aaaa)."""
    m = _ISO.match(str(fecha or ""))
    return f"{m[3]}/{m[2]}/{m[1]}" if m else fecha


def _texto_plano(texto) -> str:
    """Quita el HTML del respaldo y decodifica sus entidades (&OACUTE;, &NBSP;)."""
    texto = re.sub(r"<[^>]*>", " ", str(texto or ""))
    texto = _decodificar_entidades_satje(texto)
    return re.sub(r"\s+", " ", texto).strip()


def _unir_cuerpos(historial: list[dict]) -> list[dict]:
    """Une al rótulo de un auto el cuerpo que el historial compactado guardó aparte.

    En el histórico, «ABANDONO ... (AUTO INTERLOCUTORIO)» quedó como una fila
    sin texto y el auto («VISTOS: ... se declara el abandono») como otra fila
    del mismo día sin rótulo. Sin unirlas, la parte resolutiva nunca se lee y
    el cierre queda POR_CONFIRMAR. Solo se une a autos (no a razones ni
    constancias) cuyo detalle es su propio rótulo.
    """
    tipo_auto = re.compile(MotorInferenciaProcesal._CONDICION_TIPO_AUTO)
    cuerpos: dict[str, list[str]] = {}
    for act in historial:
        if not act["titulo"] and act["detalle"]:
            textos = cuerpos.setdefault(act["fecha"], [])
            if act["detalle"] not in textos:
                textos.append(act["detalle"])
    if not cuerpos:
        return historial
    for act in historial:
        rotulo = normalizar_texto(act["titulo"])
        if (
            rotulo and act["detalle"] == act["titulo"] and tipo_auto.search(rotulo)
            and not MotorInferenciaProcesal.PATRON_RAZON.search(rotulo)
            and act["fecha"] in cuerpos
        ):
            act["detalle"] = " ".join([act["titulo"], *cuerpos[act["fecha"]]])
    return historial


def _sin_decision() -> dict:
    """Sin historial o sin etapa no hay base para afirmar que la causa sigue vigente."""
    return {"CONDICION": "POR_CONFIRMAR", "FECHA CONDICION": None, "ACTUACION CONDICION": None}


def _condicion(filas_pg: list[tuple], numero_causa: str, payload, resumen: Counter,
               respaldo=None) -> dict:
    datos = {}
    if isinstance(payload, dict):
        datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
    # El historial del lote queda en datos_json solo en algunas causas; el
    # resto se lee del historial append-only (compactado: sin detalle).
    actuaciones = (datos.get("HISTORIAL_ACTUACIONES")
                   or _historial_guardado(filas_pg, numero_causa, respaldo, resumen))
    if not actuaciones:
        resumen["sin_historial"] += 1
        resumen["sin_actuaciones"] += 1
        return _sin_decision()
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
        resumen["sin_historial"] += 1
        resumen["sin_etapa"] += 1
        return _sin_decision()
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
        historiales = _historiales_del_lote(conn, [f[0] for f in filas])
        for numero_causa, payload, condicion_actual, version in filas:
            parcial["vistas"] += 1
            nueva = _condicion(historiales[numero_causa], numero_causa, payload, parcial, respaldo)
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
    # En seco y antes de la migración, todas cuentan como el valor por defecto de 005.
    columna = "condicion" if con_columna else "'POR_CONFIRMAR'"
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
