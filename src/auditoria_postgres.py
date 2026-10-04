"""Ejecutor NVIDIA reanudable para la fuente de verdad PostgreSQL."""

from __future__ import annotations

import json

from psycopg2.extras import Json

from src.catalogo_procesal import enriquecer_datos_procesales
from src.historial_ia import huella_contexto, normalizar_actuaciones
from src.proveedor_nvidia import (
    ErrorAuditoriaIA, VERSION_PROMPT, auditar_nvidia, construir_contexto,
)
from src.repositorio_postgres import RepositorioColaPostgres


def ejecutar_postgres(config: dict, limite: int) -> dict:
    ia = config.get("inferencia_ia") or {}
    modo = ia.get("modo", "deshabilitado")
    if modo not in {"sombra", "revision"}:
        raise ValueError("Modo de IA no implementado para PostgreSQL")
    modelo = ia.get("modelo", "nvidia/nemotron-3-super-120b-a12b")
    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    if not repo.verificar_esquema():
        raise RuntimeError("ESQUEMA_POSTGRES_INCOMPLETO")
    resumen = {"vistos": 0, "auditados": 0, "revision": 0,
               "omitidos": 0, "errores": 0, "circuito_abierto": False,
               "ultimo_error_codigo": None}
    ultima_causa = ""
    conn = repo._get_connection()
    try:
        while True:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT numero_causa, datos_json FROM expedientes
                    WHERE numero_causa > %s ORDER BY numero_causa LIMIT 20
                """, (ultima_causa,))
                filas = cursor.fetchall()
            if not filas:
                break
            for numero_causa, payload in filas:
                ultima_causa = numero_causa
                resumen["vistos"] += 1
                if not isinstance(payload, dict):
                    resumen["omitidos"] += 1
                    continue
                datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
                datos = dict(datos)
                enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
                actuaciones = normalizar_actuaciones(
                    numero_causa, datos.get("HISTORIAL_ACTUACIONES") or []
                )
                if not actuaciones:
                    resumen["omitidos"] += 1
                    continue
                huella = huella_contexto(actuaciones, datos) + ":" + VERSION_PROMPT
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT estado FROM auditorias_ia WHERE numero_causa=%s
                        AND huella_contexto=%s AND modelo=%s AND modo=%s
                    """, (numero_causa, huella, modelo, modo))
                    previa = cursor.fetchone()
                if previa and previa[0] in {"COMPLETADA", "REVISION", "INSUFICIENTE"}:
                    resumen["omitidos"] += 1
                    continue
                contexto, mapa = construir_contexto(datos, actuaciones)
                try:
                    decision, consumo = auditar_nvidia(contexto, mapa, modelo=modelo)
                    estado = "COMPLETADA"
                    if decision["decision"] == "INSUFICIENTE":
                        estado = "INSUFICIENTE"
                    elif decision["decision"] == "CORREGIR" or decision["requiere_revision_humana"]:
                        estado = "REVISION"
                    elif decision["estado_actual"] != contexto["inferencia_sistema"]["estado_actual"]:
                        estado = "REVISION"
                    error = None
                except ErrorAuditoriaIA as exc:
                    decision, consumo, estado, error = None, None, "ERROR", exc.codigo
                    resumen["errores"] += 1
                    resumen["ultimo_error_codigo"] = error
                    if error in {"HTTP_401", "HTTP_402", "NVIDIA_API_KEY_AUSENTE"}:
                        resumen["circuito_abierto"] = True
                with conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO auditorias_ia
                            (numero_causa, huella_contexto, modelo, modo, estado,
                             decision_json, consumo_json, error_codigo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (numero_causa, huella_contexto, modelo, modo)
                            DO UPDATE SET estado=EXCLUDED.estado,
                              decision_json=EXCLUDED.decision_json,
                              consumo_json=EXCLUDED.consumo_json,
                              error_codigo=EXCLUDED.error_codigo,
                              creado_en=CURRENT_TIMESTAMP
                            RETURNING id
                        """, (
                            numero_causa, huella, modelo, modo, estado,
                            Json(decision) if decision is not None else None,
                            Json(consumo) if consumo is not None else None, error,
                        ))
                        auditoria_id = cursor.fetchone()[0]
                        if estado in {"REVISION", "INSUFICIENTE"}:
                            cursor.execute("""
                                INSERT INTO revisiones_ia(auditoria_id, numero_causa)
                                VALUES (%s, %s) ON CONFLICT (auditoria_id) DO NOTHING
                            """, (auditoria_id, numero_causa))
                        if decision:
                            hito = decision.get("ultimo_hito") or {}
                            if hito.get("eta_id") and hito.get("fas_id") and decision["evidencias"]:
                                cursor.execute("""
                                    INSERT INTO hitos_procesales
                                    (numero_causa, actuacion_id, eta_id, fas_id,
                                     fuente, condicion, version)
                                    VALUES (%s, %s, %s, %s, 'NVIDIA', 'PROPUESTA', %s)
                                    ON CONFLICT (numero_causa, actuacion_id, fuente, version)
                                    DO NOTHING
                                """, (
                                    numero_causa, decision["evidencias"][0],
                                    hito["eta_id"], hito["fas_id"], VERSION_PROMPT,
                                ))
                if estado != "ERROR":
                    resumen["auditados"] += 1
                    if estado == "REVISION":
                        resumen["revision"] += 1
                if resumen["circuito_abierto"]:
                    return resumen
                if limite and resumen["auditados"] + resumen["errores"] >= limite:
                    return resumen
        return resumen
    finally:
        conn.close()
