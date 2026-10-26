"""Recalcula la condición de las causas ya guardadas sin reconsultar SATJE.

Usa el mismo historial que vio el motor (``datos_json``) y solo escribe la
condición: columnas ``condicion``, ``fecha_condicion`` y ``actuacion_condicion``
y las mismas claves dentro de ``datos_json.datos`` (para el Excel). La etapa y
la fase no se tocan. Sin ``--aplicar`` solo informa cuántas cambiarían.
"""

from __future__ import annotations

import argparse
import csv
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
        # Un "título" que es el inicio de un HTML ("<p style=...VI") no es
        # rótulo: es el comienzo del propio texto, recortado.
        es_html = str(titulo or titulo_r or "").lstrip().startswith("<")
        detalle = _texto_plano(detalle or detalle_r) or _texto_plano(titulo or titulo_r)
        titulo = "" if es_html else _texto_plano(titulo or titulo_r)
        historial.append({
            "fecha": _fecha_dia(fecha), "titulo": titulo, "detalle": detalle or titulo,
            "ORIGEN_CARPETA": carpeta,
        })
    return _unir_cuerpos(historial, resumen)


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


def _unir_cuerpos(historial: list[dict], resumen=None) -> list[dict]:
    """Une al rótulo de un auto el cuerpo que el historial compactado guardó aparte.

    En el histórico, «ABANDONO ... (AUTO INTERLOCUTORIO)» quedó como una fila
    sin texto y el auto («VISTOS: ... se declara el abandono») como otra fila
    del mismo día sin rótulo. Sin unirlas, la parte resolutiva nunca se lee y
    el cierre queda POR_CONFIRMAR.

    Ese día, en la misma carpeta, también quedan sin rótulo copias de los
    rótulos, la razón del secretario («RAZÓN: ...») y la notificación («En
    Quito, lunes ...»); solo un texto que abre con «VISTOS» es cuerpo de auto.
    Si la misma captura trae el texto con un «título» HTML, ese texto también
    es cuerpo sin rótulo (``_historial_guardado`` le quita el título).
    Se une cuando la pareja es inequívoca: un único rótulo de auto (no
    razones ni constancias) y un único cuerpo de auto. Con varios candidatos
    no se adivina: el auto queda sin texto (POR_CONFIRMAR).
    """
    tipo_auto = re.compile(MotorInferenciaProcesal._CONDICION_TIPO_AUTO)
    cuerpos: dict[tuple, list[str]] = {}
    autos: dict[tuple, dict[str, list[dict]]] = {}
    for act in historial:
        # Carpeta exacta: la huella final del código identifica dependencia e
        # incidente, así que no se compara solo el prefijo.
        clave = (act["fecha"], act.get("ORIGEN_CARPETA"))
        rotulo = normalizar_texto(act["titulo"])
        cuerpo = normalizar_texto(act["detalle"])
        if (not act["titulo"] and _PATRON_CUERPO_AUTO.match(cuerpo)
                and not _PATRON_NO_ES_AUTO.match(cuerpo)):
            textos = cuerpos.setdefault(clave, [])
            if act["detalle"] not in textos:
                textos.append(act["detalle"])
        elif (
            # Sin texto propio: el detalle es su rótulo u otro rótulo del día
            # (el respaldo a veces trae el de la razón de notificación).
            rotulo and _PATRON_SOLO_ROTULO.match(normalizar_texto(act["detalle"]))
            and tipo_auto.search(rotulo)
            and not MotorInferenciaProcesal.PATRON_RAZON.search(rotulo)
        ):
            autos.setdefault(clave, {}).setdefault(rotulo, []).append(act)
    for clave, por_rotulo in autos.items():
        textos = cuerpos.get(clave, [])
        if len(por_rotulo) == 1 and len(textos) == 1:
            repetidos = next(iter(por_rotulo.values()))
            # El cuerpo se pega a una sola fila: si el rótulo se repite no
            # consta que sean el mismo auto, y no se duplica la decisión.
            repetidos[0]["detalle"] = f"{repetidos[0]['titulo']} {textos[0]}"
            if len(repetidos) > 1 and resumen is not None:
                resumen["autos_repetidos"] += 1
        elif textos and resumen is not None:
            resumen["cuerpos_ambiguos"] += 1
    return historial


# Un auto de SATJE abre con «VISTOS», a lo sumo tras su encabezado de lugar,
# fecha y hora («QUITO, LUNES 15 DE DICIEMBRE DEL 2025, LAS 10H44.»). Una
# razón o constancia que transcribe otro auto no empieza así.
_PATRON_CUERPO_AUTO = re.compile(
    r"^\s*(?:(?:EN\s+)?[A-Z][A-Z ]{1,40},\s*"
    r"(?:LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)\b"
    r"[^.:]{0,120}?\b\d{1,2}\s*H\s*\d{2}\b[^.:]{0,40}[.:-]+\s*)?VISTOS\b"
)
# Lo que da cuenta de un auto sin ser el auto: razones, constancias, notificaciones.
_PATRON_NO_ES_AUTO = re.compile(
    r"^\s*(?:RAZON|CONSTANCIA|CERTIFICO|NOTIFICACION|NOTIFICO|OFICIO|SIENTO)\b"
)
# Un rótulo de SATJE: texto corto con el tipo de providencia entre paréntesis.
_PATRON_SOLO_ROTULO = re.compile(r"^[^()]{0,160}\([^)]*\)\s*$")


def _sin_decision() -> dict:
    """Sin historial o sin etapa no hay base para afirmar que la causa sigue vigente."""
    return {"CONDICION": "POR_CONFIRMAR", "FECHA CONDICION": None, "ACTUACION CONDICION": None}


def _condicion(filas_pg: list[tuple], numero_causa: str, payload, resumen: Counter,
               respaldo=None) -> dict:
    datos = {}
    if isinstance(payload, dict):
        datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
    # Fuente canónica: el historial append-only, que el respaldo completa
    # (texto compactado, cuerpos aparte). El historial inline de datos_json
    # solo conserva rótulos en muchas causas; se usa si no hay otro.
    inline = datos.get("HISTORIAL_ACTUACIONES")
    if filas_pg:
        actuaciones = _historial_guardado(filas_pg, numero_causa, respaldo, resumen)
        resumen["fuente_historial"] += 1
        if inline:
            resumen["inline_descartado"] += 1
    else:
        actuaciones = inline or []
        if inline:
            resumen["fuente_inline"] += 1
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


def _metadatos(condicion: dict) -> tuple:
    """Lo que se guarda en las columnas, en el mismo formato que la escritura."""
    fecha = condicion["FECHA CONDICION"]
    return (condicion["CONDICION"], str(fecha) if fecha else None,
            condicion["ACTUACION CONDICION"])


def _metadatos_json(payload) -> tuple | None:
    """Condición guardada en datos_json.datos; None si no hay objeto datos (no se escribe ahí)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("datos"), dict):
        return None
    return _metadatos({clave: payload["datos"].get(clave) for clave in
                       ("CONDICION", "FECHA CONDICION", "ACTUACION CONDICION")})


def _procesar_lote(repo, aplicar, columna, desde, tamano, resumen, respaldo=None,
                   detalle=None) -> str | None:
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
        for numero_causa, payload, actual, version in filas:
            parcial["vistas"] += 1
            nueva = _condicion(historiales[numero_causa], numero_causa, payload, parcial, respaldo)
            parcial[nueva["CONDICION"]] += 1
            if detalle is not None:
                detalle.append((numero_causa, *_metadatos(nueva)))
            # Se compara la condición con su fecha y actuación, en las columnas
            # y en datos_json.datos (lo que lee el Excel): si falta en
            # cualquiera de los dos lugares, se escribe.
            if _metadatos(nueva) == tuple(actual) and _metadatos_json(payload) in (
                None, _metadatos(nueva)
            ):
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


def _validar_ruta_privada(ruta: Path) -> None:
    """El detalle lleva números de causa: nunca dentro de un repositorio Git.

    Se comprueba antes de leer causas, para no procesar 2.000 y fallar al final.
    """
    destino = ruta.resolve()
    if not destino.parent.is_dir():
        raise RuntimeError(f"DETALLE_SIN_CARPETA: {destino.parent}")
    if any((carpeta / ".git").exists() for carpeta in (destino.parent, *destino.parents)):
        raise RuntimeError("DETALLE_DENTRO_DE_GIT: guárdelo en la carpeta privada del servidor")


def recalcular(config_path: Path, aplicar: bool = False, limite: int = 0,
               desde: str = "", intentos: int = 5, ruta_respaldo: Path | None = None,
               ruta_detalle: Path | None = None) -> dict:
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
    if ruta_detalle:
        _validar_ruta_privada(ruta_detalle)
    if aplicar and not con_columna:
        raise RuntimeError("FALTA_MIGRACION_005_CONDICION")
    if aplicar and respaldo is None:
        # Sin el texto compactado casi todo el histórico quedaría POR_CONFIRMAR.
        raise RuntimeError("FALTA_RESPALDO: use --respaldo para --aplicar")
    # En seco y antes de la migración, todas cuentan como el valor por defecto de 005.
    columna = ("ARRAY[condicion, fecha_condicion, actuacion_condicion]::text[]" if con_columna
               else "ARRAY['POR_CONFIRMAR', NULL, NULL]::text[]")
    ultima_causa = desde
    fallos = 0
    filas_detalle: list[tuple] = []
    while not (limite and resumen["vistas"] >= limite):
        tamano = min(50, limite - resumen["vistas"]) if limite else 50
        try:
            lote_detalle: list[tuple] = []
            siguiente = _procesar_lote(
                repo, aplicar, columna, ultima_causa, tamano, resumen, respaldo,
                lote_detalle if ruta_detalle else None,
            )
            # Solo se conserva el detalle de un lote terminado (no de un reintento).
            filas_detalle.extend(lote_detalle)
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
    if ruta_detalle:
        # Contiene números de causa: va a la carpeta privada, nunca a coordinación.
        with ruta_detalle.open("w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(("numero_causa", "condicion", "fecha_condicion", "actuacion_condicion"))
            escritor.writerows(filas_detalle)
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
    parser.add_argument("--detalle", type=Path,
                        help="CSV con la condición de cada causa (contiene números de causa: "
                             "guardarlo en la carpeta privada) para comparar corridas por causa")
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    print(json.dumps(recalcular(args.config, args.aplicar, args.limite, args.desde,
                                ruta_respaldo=args.respaldo, ruta_detalle=args.detalle),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
