"""Vistas de auditoría de IA para el Excel profesional."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from src.proveedor_nvidia import VERSION_PROMPT


COLUMNAS_HITOS = [
    "NUMERO_JUICIO", "ACTUACION_ID", "FECHA", "CARPETA", "eta_id",
    "fas_id", "CONDICION", "FUENTE", "VERSION",
]
COLUMNAS_REVISION = [
    "AUDITORIA_ID", "NUMERO_JUICIO", "ESTADO", "ETAPA SISTEMA",
    "FASE SISTEMA", "eta_id IA", "fas_id IA", "EVIDENCIAS",
    "CONFIANZA IA", "MOTIVO IA", "DECISION HUMANA", "eta_id MANUAL",
    "fas_id MANUAL", "OBSERVACION HUMANA",
]
COLUMNAS_RESUMEN = [
    "ESTADO AUDITORIA IA", "FUENTE DECISION", "CONFIANZA IA",
    "REVISION PENDIENTE",
]


def _leer_json(texto):
    if isinstance(texto, dict):
        return texto
    try:
        valor = json.loads(texto or "{}")
        return valor if isinstance(valor, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _auditoria_vigente(decision):
    version = str(decision.get("version_prompt") or "")
    return not version.startswith("auditoria-nvidia-") or version == VERSION_PROMPT


def _hito_vigente(version):
    version = str(version or "")
    return not version.startswith("auditoria-nvidia-") or version == VERSION_PROMPT


def preparar_vistas_ia(ruta_db: str | Path, reporte: pd.DataFrame):
    """Añade estado visible a Reporte y construye las hojas de hitos/revisión."""
    reporte = reporte.copy()
    for columna in COLUMNAS_RESUMEN:
        if columna == "CONFIANZA IA":
            reporte[columna] = pd.Series([None] * len(reporte), index=reporte.index,
                                         dtype=object)
        else:
            reporte[columna] = "NO" if columna == "REVISION PENDIENTE" else ""
    reporte["FUENTE DECISION"] = "REGLAS"
    hitos = pd.DataFrame(columns=COLUMNAS_HITOS)
    revisiones = pd.DataFrame(columns=COLUMNAS_REVISION)
    if not Path(ruta_db).is_file():
        return reporte, hitos, revisiones
    with closing(sqlite3.connect(str(ruta_db), timeout=10)) as conn:
        tablas = {fila[0] for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"auditorias_ia", "revisiones_ia", "hitos_procesales"} <= tablas:
            return reporte, hitos, revisiones
        ultimas = {}
        for fila in conn.execute("""
            SELECT id, numero_causa, estado, decision_json FROM auditorias_ia
            ORDER BY id DESC
        """):
            if _auditoria_vigente(_leer_json(fila[3])):
                ultimas.setdefault(fila[1], fila)
        if "NUMERO_JUICIO" in reporte.columns:
            for indice, causa in reporte["NUMERO_JUICIO"].items():
                fila = ultimas.get(str(causa).strip())
                if not fila:
                    reporte.at[indice, "ESTADO AUDITORIA IA"] = "PENDIENTE"
                    continue
                _id, _numero, estado, decision_json = fila
                decision = _leer_json(decision_json)
                reporte.at[indice, "ESTADO AUDITORIA IA"] = estado
                reporte.at[indice, "CONFIANZA IA"] = decision.get("confianza", "")
                reporte.at[indice, "REVISION PENDIENTE"] = (
                    "SI" if estado in {"REVISION", "INSUFICIENTE"} else "NO"
                )
                if estado == "COMPLETADA":
                    reporte.at[indice, "FUENTE DECISION"] = "REGLAS AUDITADAS"
        filas_hitos = list(conn.execute("""
            SELECT h.numero_causa, h.actuacion_id, a.fecha, a.carpeta,
                   h.eta_id, h.fas_id, h.condicion, h.fuente, h.version
            FROM hitos_procesales h
            LEFT JOIN actuaciones_procesales a
              ON a.actuacion_id = h.actuacion_id
            ORDER BY h.numero_causa, a.fecha, h.id
        """))
        hitos = pd.DataFrame(
            [fila for fila in filas_hitos if _hito_vigente(fila[8])],
            columns=COLUMNAS_HITOS,
        )
        filas_revision = []
        for fila in conn.execute("""
            SELECT r.auditoria_id, r.numero_causa, r.estado, a.decision_json,
                   e.estado_json, r.decision_humana, r.eta_id_manual,
                   r.fas_id_manual, r.observacion
            FROM revisiones_ia r
            JOIN auditorias_ia a ON a.id = r.auditoria_id
            LEFT JOIN ejecuciones_inferencia e ON e.id = (
                SELECT MAX(e2.id) FROM ejecuciones_inferencia e2
                WHERE e2.numero_causa = r.numero_causa
            )
            ORDER BY r.id
        """):
            auditoria_id, causa, estado, decision_json, estado_json, \
                humana, eta_manual, fas_manual, observacion = fila
            decision = _leer_json(decision_json)
            if not _auditoria_vigente(decision):
                continue
            sistema = _leer_json(estado_json)
            actual = decision.get("estado_actual") or {}
            filas_revision.append((
                auditoria_id, causa, estado, sistema.get("ETAPA ACTUAL"),
                sistema.get("FASE ACTUAL"), actual.get("eta_id"),
                actual.get("fas_id"), ", ".join(decision.get("evidencias") or []),
                decision.get("confianza"), decision.get("motivo"),
                humana, eta_manual, fas_manual, observacion,
            ))
        revisiones = pd.DataFrame(filas_revision, columns=COLUMNAS_REVISION)
    return reporte, hitos, revisiones


def preparar_vistas_ia_postgres(config: dict, reporte: pd.DataFrame):
    """Construye las mismas vistas desde la fuente concurrente PostgreSQL."""
    from src.repositorio_postgres import RepositorioColaPostgres

    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    reporte = reporte.copy()
    reporte["ESTADO AUDITORIA IA"] = "PENDIENTE"
    reporte["FUENTE DECISION"] = "REGLAS"
    reporte["CONFIANZA IA"] = pd.Series([None] * len(reporte),
                                         index=reporte.index, dtype=object)
    reporte["REVISION PENDIENTE"] = "NO"
    with repo._connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT ON (numero_causa)
                    id, numero_causa, estado, decision_json
                FROM auditorias_ia ORDER BY numero_causa, id DESC
            """)
            ultimas = {fila[1]: fila for fila in cursor.fetchall()
                       if _auditoria_vigente(_leer_json(fila[3]))}
            cursor.execute("""
                SELECT h.numero_causa, h.actuacion_id, a.fecha, a.carpeta,
                       h.eta_id, h.fas_id, h.condicion, h.fuente, h.version
                FROM hitos_procesales h
                LEFT JOIN actuaciones_procesales a
                  ON a.actuacion_id = h.actuacion_id
                ORDER BY h.numero_causa, a.fecha, h.id
            """)
            hitos = pd.DataFrame(
                [fila for fila in cursor.fetchall() if _hito_vigente(fila[8])],
                columns=COLUMNAS_HITOS,
            )
            cursor.execute("""
                SELECT r.auditoria_id, r.numero_causa, r.estado,
                       a.decision_json, e.estado_json, r.decision_humana,
                       r.eta_id_manual, r.fas_id_manual, r.observacion
                FROM revisiones_ia r
                JOIN auditorias_ia a ON a.id = r.auditoria_id
                LEFT JOIN LATERAL (
                    SELECT estado_json FROM ejecuciones_inferencia e2
                    WHERE e2.numero_causa = r.numero_causa
                    ORDER BY e2.id DESC LIMIT 1
                ) e ON TRUE
                ORDER BY r.id
            """)
            filas_revision = []
            for fila in cursor.fetchall():
                auditoria_id, causa, estado, decision_json, estado_json, \
                    humana, eta_manual, fas_manual, observacion = fila
                decision = _leer_json(decision_json)
                if not _auditoria_vigente(decision):
                    continue
                sistema = _leer_json(estado_json)
                actual = decision.get("estado_actual") or {}
                filas_revision.append((
                    auditoria_id, causa, estado, sistema.get("ETAPA ACTUAL"),
                    sistema.get("FASE ACTUAL"), actual.get("eta_id"),
                    actual.get("fas_id"), ", ".join(decision.get("evidencias") or []),
                    decision.get("confianza"), decision.get("motivo"),
                    humana, eta_manual, fas_manual, observacion,
                ))
            revisiones = pd.DataFrame(filas_revision, columns=COLUMNAS_REVISION)
    if "NUMERO_JUICIO" in reporte.columns:
        for indice, causa in reporte["NUMERO_JUICIO"].items():
            fila = ultimas.get(str(causa).strip())
            if not fila:
                continue
            _id, _numero, estado, decision_json = fila
            decision = _leer_json(decision_json)
            reporte.at[indice, "ESTADO AUDITORIA IA"] = estado
            reporte.at[indice, "CONFIANZA IA"] = decision.get("confianza")
            reporte.at[indice, "REVISION PENDIENTE"] = (
                "SI" if estado in {"REVISION", "INSUFICIENTE"} else "NO"
            )
            if estado == "COMPLETADA":
                reporte.at[indice, "FUENTE DECISION"] = "REGLAS AUDITADAS"
    return reporte, hitos, revisiones
