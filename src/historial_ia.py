"""Historial procesal y auditorías de IA anexas a la fotografía del expediente.

Las tablas de este módulo son aditivas: ``resultados_expediente`` continúa siendo
la fotografía operativa y ninguna propuesta de IA la modifica.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from typing import Any, Iterable


VERSION_ESQUEMA = "historial-ia-1"


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


LONGITUD_TITULO_DERIVADO = 160


def titulo_desde_detalle(detalle: str) -> str:
    """Primera línea con texto del detalle, sin HTML, como título de respaldo."""
    plano = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", detalle)
    plano = html.unescape(re.sub(r"<[^>]*>", "", plano))
    for linea in plano.splitlines():
        linea = " ".join(linea.split())
        if linea:
            if len(linea) <= LONGITUD_TITULO_DERIVADO:
                return linea
            return linea[: LONGITUD_TITULO_DERIVADO - 1].rstrip() + "…"
    return ""


def datos_resultado(resultado: dict[str, Any]) -> dict[str, Any]:
    datos = resultado.get("datos")
    return datos if isinstance(datos, dict) else resultado


def normalizar_actuaciones(
    numero_causa: str, actuaciones: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Conserva el original y asigna una identidad estable a cada actuación.

    Nunca devuelve actuaciones sin texto: las que no traen título ni detalle se descartan
    y las que solo traen detalle reciben como título su primera línea. La identidad se
    calcula con el contenido original, así que no cambia para las actuaciones ya guardadas.
    """
    normalizadas = []
    vistos = set()
    for actuacion in actuaciones:
        if not isinstance(actuacion, dict):
            continue
        fecha = _texto(actuacion.get("fecha") or actuacion.get("FECHA"))
        carpeta = _texto(actuacion.get("ORIGEN_CARPETA") or actuacion.get("carpeta"))
        titulo = _texto(
            actuacion.get("titulo") or actuacion.get("tipo")
            or actuacion.get("actuacion") or actuacion.get("nombre")
        )
        detalle = _texto(actuacion.get("detalle") or actuacion.get("descripcion"))
        if not titulo and not detalle:
            continue
        contenido = {
            "causa": _texto(numero_causa), "carpeta": carpeta,
            "fecha": fecha, "titulo": titulo, "detalle": detalle,
        }
        huella = hashlib.sha256(_json(contenido).encode("utf-8")).hexdigest()
        identificador = "ACT-" + huella[:24]
        if identificador in vistos:
            continue
        vistos.add(identificador)
        titulo = titulo or titulo_desde_detalle(detalle)
        if not titulo:
            continue
        normalizadas.append({
            "actuacion_id": identificador,
            "numero_causa": _texto(numero_causa),
            "carpeta": carpeta,
            "fecha": fecha,
            "titulo": titulo,
            "detalle": detalle,
            "contenido_sha256": huella,
            # El texto completo ya vive en ``detalle``; el JSON conserva el
            # resto de metadatos sin duplicar cientos de MB en la tabla.
            "datos_json": _json({
                clave: valor for clave, valor in actuacion.items()
                if clave not in {"detalle", "descripcion"}
            }),
        })
    return normalizadas


def inicializar_esquema(conn: sqlite3.Connection) -> None:
    """Crea tablas nuevas sin reescribir resultados históricos."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS actuaciones_procesales (
            actuacion_id TEXT PRIMARY KEY,
            numero_causa TEXT NOT NULL,
            carpeta TEXT NOT NULL,
            fecha TEXT NOT NULL,
            titulo TEXT NOT NULL,
            detalle TEXT NOT NULL,
            contenido_sha256 TEXT NOT NULL,
            datos_json TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_actuaciones_causa
            ON actuaciones_procesales(numero_causa, fecha);
        CREATE TABLE IF NOT EXISTS ejecuciones_inferencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_causa TEXT NOT NULL,
            huella_contexto TEXT NOT NULL,
            version_reglas TEXT NOT NULL,
            estado_json TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(numero_causa, huella_contexto, version_reglas)
        );
        CREATE TABLE IF NOT EXISTS auditorias_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_causa TEXT NOT NULL,
            huella_contexto TEXT NOT NULL,
            modelo TEXT NOT NULL,
            modo TEXT NOT NULL,
            estado TEXT NOT NULL,
            decision_json TEXT,
            consumo_json TEXT,
            error_codigo TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(numero_causa, huella_contexto, modelo, modo)
        );
        CREATE INDEX IF NOT EXISTS idx_auditorias_causa
            ON auditorias_ia(numero_causa, creado_en);
        CREATE TABLE IF NOT EXISTS revisiones_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER NOT NULL UNIQUE,
            numero_causa TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'PENDIENTE',
            decision_humana TEXT,
            eta_id_manual INTEGER,
            fas_id_manual INTEGER,
            observacion TEXT,
            revisado_en TEXT,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias_ia(id)
        );
        CREATE TABLE IF NOT EXISTS hitos_procesales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_causa TEXT NOT NULL,
            actuacion_id TEXT NOT NULL,
            eta_id INTEGER,
            fas_id INTEGER,
            fuente TEXT NOT NULL,
            condicion TEXT NOT NULL,
            version TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(numero_causa, actuacion_id, fuente, version)
        );
    """)


def huella_contexto(actuaciones: list[dict[str, Any]], datos: dict[str, Any]) -> str:
    estado = {
        "actuaciones": sorted(act["actuacion_id"] for act in actuaciones),
        "ultima": [datos.get("eta_id ULTIMA ETAPA"), datos.get("fas_id ULTIMA FASE")],
        "actual": [datos.get("eta_id ETAPA ACTUAL"), datos.get("fas_id FASE ACTUAL")],
        "fase": datos.get("FASE ACTUAL") or datos.get("FASE_PROCESAL"),
    }
    return hashlib.sha256(_json(estado).encode("utf-8")).hexdigest()


def registrar_historial(
    conn: sqlite3.Connection, numero_causa: str, resultado: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    """Registra actuaciones y estado determinista en la transacción existente."""
    datos = datos_resultado(resultado)
    actuaciones = normalizar_actuaciones(
        numero_causa, datos.get("HISTORIAL_ACTUACIONES") or []
    )
    for act in actuaciones:
        conn.execute("""
            INSERT OR IGNORE INTO actuaciones_procesales
            (actuacion_id, numero_causa, carpeta, fecha, titulo, detalle,
             contenido_sha256, datos_json)
            VALUES (:actuacion_id, :numero_causa, :carpeta, :fecha, :titulo,
                    :detalle, :contenido_sha256, :datos_json)
        """, act)
    huella = huella_contexto(actuaciones, datos)
    if actuaciones:
        estado = {
            campo: datos.get(campo) for campo in (
                "ULTIMA ETAPA", "ULTIMA FASE", "ETAPA ACTUAL", "FASE ACTUAL",
                "FECHA FIN ULTIMA FASE", "FECHA INICIO FASE ACTUAL",
                "eta_id ULTIMA ETAPA", "fas_id ULTIMA FASE",
                "eta_id ETAPA ACTUAL", "fas_id FASE ACTUAL",
            )
        }
        conn.execute("""
            INSERT OR IGNORE INTO ejecuciones_inferencia
            (numero_causa, huella_contexto, version_reglas, estado_json)
            VALUES (?, ?, ?, ?)
        """, (numero_causa, huella, VERSION_ESQUEMA, _json(estado)))
    return actuaciones, huella


def registrar_auditoria(
    conn: sqlite3.Connection, *, numero_causa: str, huella: str,
    modelo: str, modo: str, estado: str, decision: dict[str, Any] | None = None,
    consumo: dict[str, Any] | None = None, error_codigo: str | None = None,
) -> int:
    conn.execute("""
        INSERT INTO auditorias_ia
        (numero_causa, huella_contexto, modelo, modo, estado, decision_json,
         consumo_json, error_codigo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(numero_causa, huella_contexto, modelo, modo) DO UPDATE SET
            estado=excluded.estado,
            decision_json=excluded.decision_json,
            consumo_json=excluded.consumo_json,
            error_codigo=excluded.error_codigo,
            creado_en=CURRENT_TIMESTAMP
    """, (
        numero_causa, huella, modelo, modo, estado,
        _json(decision) if decision is not None else None,
        _json(consumo) if consumo is not None else None,
        error_codigo,
    ))
    fila = conn.execute("""
        SELECT id FROM auditorias_ia WHERE numero_causa=? AND huella_contexto=?
            AND modelo=? AND modo=?
    """, (numero_causa, huella, modelo, modo)).fetchone()
    auditoria_id = int(fila[0])
    if estado in {"REVISION", "INSUFICIENTE"} or (
        decision and decision.get("requiere_revision_humana")
    ):
        conn.execute("""
            INSERT OR IGNORE INTO revisiones_ia (auditoria_id, numero_causa)
            VALUES (?, ?)
        """, (auditoria_id, numero_causa))
    return auditoria_id
