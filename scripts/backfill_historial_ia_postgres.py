"""Normaliza historiales ya guardados en PostgreSQL sin reconsultar SATJE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from psycopg2.extras import Json, execute_values

from src.catalogo_procesal import enriquecer_datos_procesales
from src.historial_ia import VERSION_ESQUEMA, huella_contexto, normalizar_actuaciones
from src.repositorio_postgres import RepositorioColaPostgres


def migrar(config_path: Path, limite: int = 0) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    repo = RepositorioColaPostgres.desde_config(config.get("base_de_datos"))
    if not repo.verificar_esquema():
        raise RuntimeError("ESQUEMA_POSTGRES_INCOMPLETO")
    resumen = {"vistos": 0, "migrados": 0, "omitidos": 0,
               "sin_historial": 0, "actuaciones_nuevas": 0}
    conn = repo._get_connection()
    ultima_causa = ""
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
                    resumen["sin_historial"] += 1
                    continue
                datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
                if not isinstance(datos, dict):
                    resumen["sin_historial"] += 1
                    continue
                datos = dict(datos)
                enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
                actuaciones = normalizar_actuaciones(
                    numero_causa, datos.get("HISTORIAL_ACTUACIONES") or []
                )
                if not actuaciones:
                    resumen["sin_historial"] += 1
                    continue
                huella = huella_contexto(actuaciones, datos)
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 1 FROM ejecuciones_inferencia
                        WHERE numero_causa=%s AND huella_contexto=%s
                          AND version_reglas=%s
                    """, (numero_causa, huella, VERSION_ESQUEMA))
                    if cursor.fetchone():
                        resumen["omitidos"] += 1
                        continue
                    valores = [(
                        act["actuacion_id"], act["numero_causa"], act["carpeta"],
                        act["fecha"], act["titulo"], act["detalle"],
                        act["contenido_sha256"], Json(json.loads(act["datos_json"])),
                    ) for act in actuaciones]
                    execute_values(cursor, """
                        INSERT INTO actuaciones_procesales
                        (actuacion_id, numero_causa, carpeta, fecha, titulo,
                         detalle, contenido_sha256, datos_json) VALUES %s
                        ON CONFLICT (actuacion_id) DO NOTHING
                    """, valores)
                    estado = {campo: datos.get(campo) for campo in (
                        "ULTIMA ETAPA", "ULTIMA FASE", "ETAPA ACTUAL",
                        "FASE ACTUAL", "FECHA FIN ULTIMA FASE",
                        "FECHA INICIO FASE ACTUAL", "eta_id ULTIMA ETAPA",
                        "fas_id ULTIMA FASE", "eta_id ETAPA ACTUAL",
                        "fas_id FASE ACTUAL",
                    )}
                    cursor.execute("""
                        INSERT INTO ejecuciones_inferencia
                        (numero_causa, huella_contexto, version_reglas, estado_json)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (numero_causa, huella_contexto, version_reglas)
                        DO NOTHING
                    """, (numero_causa, huella, VERSION_ESQUEMA, Json(estado)))
                conn.commit()
                resumen["migrados"] += 1
                resumen["actuaciones_nuevas"] += len(actuaciones)
                if limite and resumen["migrados"] >= limite:
                    return resumen
        return resumen
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--limite", type=int, default=0,
                        help="0 procesa todos los expedientes pendientes")
    args = parser.parse_args()
    if args.limite < 0:
        parser.error("--limite debe ser mayor o igual a 0")
    print(json.dumps(migrar(args.config.resolve(), args.limite),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
