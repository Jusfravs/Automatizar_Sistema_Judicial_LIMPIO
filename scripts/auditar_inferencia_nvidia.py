"""Audita expedientes persistidos con NVIDIA sin alterar su estado oficial.

Ejemplo: python -m scripts.auditar_inferencia_nvidia --config config.json --limite 10
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from src.historial_ia import (
    datos_resultado, huella_contexto, inicializar_esquema,
    normalizar_actuaciones, registrar_auditoria, registrar_historial,
)
from src.proveedor_nvidia import (
    ErrorAuditoriaIA, MODELO_PREDETERMINADO, VERSION_PROMPT,
    auditar_nvidia, construir_contexto,
)


def ejecutar(ruta_config: Path, limite: int, solo_migrar: bool = False) -> dict:
    config = json.loads(ruta_config.read_text(encoding="utf-8-sig"))
    if config.get("base_de_datos", {}).get("motor") == "postgres":
        if solo_migrar:
            from scripts.backfill_historial_ia_postgres import migrar
            return migrar(ruta_config, limite)
        from src.auditoria_postgres import ejecutar_postgres
        return ejecutar_postgres(config, limite)
    ia_config = config.get("inferencia_ia") or {}
    modo = ia_config.get("modo", "deshabilitado")
    if modo not in {"sombra", "revision", "deshabilitado"}:
        raise ValueError("Modo de IA no implementado; use sombra o revision")
    if not solo_migrar and modo == "deshabilitado":
        raise ValueError("La IA está deshabilitada en la configuración")
    modelo = ia_config.get("modelo", MODELO_PREDETERMINADO)
    ruta_db = Path(config["rutas"]["archivo_db"])
    if not ruta_db.is_absolute():
        ruta_db = ruta_config.parent / ruta_db
    if not ruta_db.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {ruta_db}")
    resumen = {"vistos": 0, "migrados": 0, "auditados": 0,
               "revision": 0, "omitidos": 0, "errores": 0,
               "circuito_abierto": False, "ultimo_error_codigo": None}
    with closing(sqlite3.connect(ruta_db, timeout=30)) as conn:
        inicializar_esquema(conn)
        cursor = conn.execute("""
            SELECT numero_causa, datos_json FROM resultados_expediente
            ORDER BY numero_causa
        """)
        for numero_causa, datos_json in cursor:
            procesados = (resumen["migrados"] if solo_migrar else
                          resumen["auditados"] + resumen["errores"])
            if limite and procesados >= limite:
                break
            resumen["vistos"] += 1
            try:
                resultado = json.loads(datos_json)
                if not isinstance(resultado, dict):
                    raise ValueError("RESULTADO_NO_OBJETO")
                datos = datos_resultado(resultado)
                actuaciones = normalizar_actuaciones(
                    numero_causa, datos.get("HISTORIAL_ACTUACIONES") or []
                )
                if not actuaciones:
                    resumen["omitidos"] += 1
                    continue
                huella = huella_contexto(actuaciones, datos)
                existe_historial = conn.execute("""
                    SELECT 1 FROM ejecuciones_inferencia
                    WHERE numero_causa=? AND huella_contexto=? LIMIT 1
                """, (numero_causa, huella)).fetchone()
                if not existe_historial:
                    registrar_historial(conn, numero_causa, resultado)
                    conn.commit()
                    resumen["migrados"] += 1
                if solo_migrar:
                    continue
                huella_versionada = huella + ":" + VERSION_PROMPT
                previa = conn.execute("""
                    SELECT estado FROM auditorias_ia WHERE numero_causa=?
                    AND huella_contexto=? AND modelo=? AND modo=?
                """, (numero_causa, huella_versionada, modelo, modo)).fetchone()
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
                    registrar_auditoria(
                        conn, numero_causa=numero_causa, huella=huella_versionada,
                        modelo=modelo, modo=modo, estado=estado,
                        decision=decision, consumo=consumo,
                    )
                    hito = decision.get("ultimo_hito") or {}
                    if hito.get("eta_id") and hito.get("fas_id") and decision["evidencias"]:
                        conn.execute("""
                            INSERT OR IGNORE INTO hitos_procesales
                            (numero_causa, actuacion_id, eta_id, fas_id,
                             fuente, condicion, version)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            numero_causa, decision["evidencias"][0],
                            hito["eta_id"], hito["fas_id"],
                            "NVIDIA", "PROPUESTA", VERSION_PROMPT,
                        ))
                    resumen["auditados"] += 1
                    if estado == "REVISION":
                        resumen["revision"] += 1
                except ErrorAuditoriaIA as exc:
                    registrar_auditoria(
                        conn, numero_causa=numero_causa, huella=huella_versionada,
                        modelo=modelo, modo=modo, estado="ERROR",
                        error_codigo=exc.codigo,
                    )
                    resumen["errores"] += 1
                    resumen["ultimo_error_codigo"] = exc.codigo
                    if exc.codigo in {"HTTP_401", "HTTP_402", "NVIDIA_API_KEY_AUSENTE"}:
                        resumen["circuito_abierto"] = True
                        conn.commit()
                        break
                conn.commit()
            except (json.JSONDecodeError, ValueError, TypeError):
                resumen["errores"] += 1
                conn.rollback()
    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--limite", type=int, default=10,
                        help="Máximo de expedientes por ejecución; 0 procesa todos")
    parser.add_argument("--solo-migrar", action="store_true",
                        help="Normalizar el historial sin llamadas a NVIDIA")
    parser.add_argument("--seguir", action="store_true",
                        help="Auditar nuevos expedientes continuamente; detener con Ctrl+C")
    parser.add_argument("--intervalo", type=int, default=60,
                        help="Segundos entre revisiones cuando se usa --seguir")
    args = parser.parse_args()
    if args.limite < 0:
        parser.error("--limite debe ser mayor o igual a 0")
    if args.intervalo < 5:
        parser.error("--intervalo debe ser al menos 5 segundos")
    if args.seguir and args.solo_migrar:
        parser.error("--seguir no se combina con --solo-migrar")
    try:
        while True:
            resumen = ejecutar(args.config.resolve(), args.limite, args.solo_migrar)
            print(json.dumps(resumen, ensure_ascii=False), flush=True)
            if not args.seguir or resumen["circuito_abierto"]:
                break
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("Auditor NVIDIA detenido.")


if __name__ == "__main__":
    main()
