"""Importacion idempotente y auditable de SQLite hacia PostgreSQL."""

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import Json


sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.catalogo_procesal import enriquecer_datos_procesales
from src.repositorio_postgres import RepositorioColaPostgres
from src.ultima_gestion import enriquecer_ultima_gestion_judicial


@dataclass(frozen=True)
class FuenteSQLite:
    nombre: str
    ruta: Path
    ciudad: str
    prioridad: int


FUENTES_PREDETERMINADAS = (
    FuenteSQLite("GENERAL", RAIZ / "data" / "estado_casos_20260827.db", "TODAS", 30),
    FuenteSQLite("QUITO", RAIZ / "data" / "quito" / "estado_casos_quito.db", "QUITO", 20),
    FuenteSQLite(
        "SANTO_DOMINGO",
        RAIZ / "data" / "santo_domingo" / "estado_casos_lstodomingo.db",
        "SANTO DOMINGO",
        10,
    ),
)


def _conexion_lectura(ruta):
    return sqlite3.connect("file:%s?mode=ro" % ruta.as_posix(), uri=True)


def _parsear_fecha(valor):
    if not valor:
        return None
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def inspeccionar_fuentes(fuentes=FUENTES_PREDETERMINADAS):
    resumen = {
        "filas_cola": 0,
        "resultados": 0,
        "causas_unicas": 0,
        "json_invalidos": 0,
        "faltantes": [],
        "por_fuente": {},
        "solapamientos": {},
    }
    causas_por_fuente = {}
    for fuente in fuentes:
        if not fuente.ruta.exists():
            resumen["faltantes"].append(str(fuente.ruta))
            continue
        with closing(_conexion_lectura(fuente.ruta)) as conn:
            causas = {fila[0] for fila in conn.execute("SELECT numero_causa FROM juicios")}
            resultados = conn.execute(
                "SELECT datos_json FROM resultados_expediente"
            ).fetchall()
        invalidos = 0
        for (contenido,) in resultados:
            try:
                json.loads(contenido)
            except (TypeError, json.JSONDecodeError):
                invalidos += 1
        causas_por_fuente[fuente.nombre] = causas
        resumen["por_fuente"][fuente.nombre] = {
            "cola": len(causas),
            "resultados": len(resultados),
            "json_invalidos": invalidos,
        }
        resumen["filas_cola"] += len(causas)
        resumen["resultados"] += len(resultados)
        resumen["json_invalidos"] += invalidos

    nombres = list(causas_por_fuente)
    for indice, nombre_a in enumerate(nombres):
        for nombre_b in nombres[indice + 1 :]:
            clave = "%s__%s" % (nombre_a, nombre_b)
            resumen["solapamientos"][clave] = len(
                causas_por_fuente[nombre_a] & causas_por_fuente[nombre_b]
            )
    if causas_por_fuente:
        resumen["causas_unicas"] = len(set().union(*causas_por_fuente.values()))
    return resumen


def _hash_version(fuente, causa, actualizado_en, contenido):
    material = "\x1f".join(
        (fuente.nombre, str(causa), str(actualizado_en or ""), str(contenido or ""))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _estado_resultado(payload, estado_cola, datos):
    estado_payload = payload.get("estado")
    if estado_payload == "EXCLUIDO_NO_CORRESPONDE":
        return "EXCLUIDO_NO_CORRESPONDE"
    if estado_payload == "PARCIAL":
        return "PARCIAL"
    if estado_payload == "SIN_RESULTADOS":
        return "SIN_RESULTADOS"
    if estado_payload == "COMPLETADO" or datos.get("ULTIMA FASE"):
        return "PROCESADO"
    return estado_cola or "PENDIENTE"


def _insertar_fotografia_actual(cur, fuente, causa, estado, origen, payload, fecha_fuente):
    datos = dict(payload.get("datos") or {})
    enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
    enriquecer_ultima_gestion_judicial(datos)
    payload = dict(payload)
    payload["datos"] = datos
    campos = RepositorioColaPostgres._campos_expediente(datos)
    actuaciones = datos.get("HISTORIAL_ACTUACIONES") or []
    cur.execute(
        """
        INSERT INTO expedientes (
            numero_causa, ciudad, estado,
            eta_id_ultima_etapa, ultima_etapa,
            fas_id_ultima_fase, ultima_fase, fecha_fin_ultima_fase,
            eta_id_etapa_actual, etapa_actual,
            fas_id_fase_actual, fase_actual, fecha_inicio_fase_actual,
            mensaje_especial, actor, demandado, tipo_accion,
            fecha_inicio_juicio, total_actuaciones, origen, datos_json,
            fuente_migracion, fuente_prioridad, version_fuente_en, actualizado_en
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (numero_causa) DO UPDATE SET
            ciudad = EXCLUDED.ciudad,
            estado = EXCLUDED.estado,
            eta_id_ultima_etapa = EXCLUDED.eta_id_ultima_etapa,
            ultima_etapa = EXCLUDED.ultima_etapa,
            fas_id_ultima_fase = EXCLUDED.fas_id_ultima_fase,
            ultima_fase = EXCLUDED.ultima_fase,
            fecha_fin_ultima_fase = EXCLUDED.fecha_fin_ultima_fase,
            eta_id_etapa_actual = EXCLUDED.eta_id_etapa_actual,
            etapa_actual = EXCLUDED.etapa_actual,
            fas_id_fase_actual = EXCLUDED.fas_id_fase_actual,
            fase_actual = EXCLUDED.fase_actual,
            fecha_inicio_fase_actual = EXCLUDED.fecha_inicio_fase_actual,
            mensaje_especial = EXCLUDED.mensaje_especial,
            actor = EXCLUDED.actor,
            demandado = EXCLUDED.demandado,
            tipo_accion = EXCLUDED.tipo_accion,
            fecha_inicio_juicio = EXCLUDED.fecha_inicio_juicio,
            total_actuaciones = EXCLUDED.total_actuaciones,
            origen = EXCLUDED.origen,
            datos_json = EXCLUDED.datos_json,
            fuente_migracion = EXCLUDED.fuente_migracion,
            fuente_prioridad = EXCLUDED.fuente_prioridad,
            version_fuente_en = EXCLUDED.version_fuente_en,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE expedientes.version_fuente_en IS NULL
           OR EXCLUDED.version_fuente_en > expedientes.version_fuente_en
           OR (
                EXCLUDED.version_fuente_en = expedientes.version_fuente_en
                AND EXCLUDED.fuente_prioridad > expedientes.fuente_prioridad
           )
        RETURNING numero_causa
        """,
        (
            causa,
            fuente.ciudad,
            estado,
            campos["eta_id_ultima"],
            campos["ultima_etapa"],
            campos["fas_id_ultima"],
            campos["ultima_fase"],
            str(campos["fecha_fin"]) if campos["fecha_fin"] else None,
            campos["eta_id_actual"],
            campos["etapa_actual"],
            campos["fas_id_actual"],
            campos["fase_actual"],
            str(campos["fecha_inicio_actual"]) if campos["fecha_inicio_actual"] else None,
            campos["mensaje"],
            campos["actor"],
            campos["demandado"],
            campos["tipo_accion"],
            str(campos["fecha_inicio_juicio"]) if campos["fecha_inicio_juicio"] else None,
            len(actuaciones),
            origen,
            Json(payload),
            fuente.nombre,
            fuente.prioridad,
            fecha_fuente,
        ),
    )
    vigente = cur.fetchone() is not None
    if vigente:
        cur.execute("DELETE FROM actuaciones WHERE numero_causa = %s", (causa,))
        for indice, actuacion in enumerate(actuaciones, start=1):
            cur.execute(
                """
                INSERT INTO actuaciones (
                    numero_causa, fecha, tipo_actuacion, detalle, instancia, orden
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    causa,
                    str(actuacion.get("fecha") or ""),
                    actuacion.get("actuacion") or actuacion.get("tipo") or "",
                    actuacion.get("detalle") or "",
                    actuacion.get("instancia") or "PRIMERA INSTANCIA",
                    indice,
                ),
            )
    return vigente


def migrar_fuente(repo, fuente):
    if not fuente.ruta.exists():
        raise FileNotFoundError(fuente.ruta)
    insertadas = 0
    invalidas = 0
    with closing(_conexion_lectura(fuente.ruta)) as sqlite_conn:
        estados = {
            fila[0]: {"estado": fila[1], "reintentos": fila[2] or 0}
            for fila in sqlite_conn.execute(
                "SELECT numero_causa, estado, reintentos FROM juicios"
            )
        }
        resultados = sqlite_conn.execute(
            """
            SELECT numero_causa, origen, datos_json, ruta_html, actualizado_en
            FROM resultados_expediente
            ORDER BY actualizado_en, numero_causa
            """
        ).fetchall()
        try:
            eventos = sqlite_conn.execute(
                "SELECT id, numero_causa, origen, detalle, creado_en FROM eventos_extraccion"
            ).fetchall()
        except sqlite3.OperationalError:
            eventos = []

    causas_con_resultado = set()
    with repo._connection() as pg_conn:
        with pg_conn.cursor() as cur:
            for causa, origen, contenido, _ruta_html, actualizado_en in resultados:
                causas_con_resultado.add(causa)
                try:
                    payload = json.loads(contenido)
                except (TypeError, json.JSONDecodeError):
                    invalidas += 1
                    continue
                datos = dict(payload.get("datos") or {})
                enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
                enriquecer_ultima_gestion_judicial(datos)
                payload["datos"] = datos
                estado = _estado_resultado(
                    payload,
                    estados.get(causa, {}).get("estado"),
                    datos,
                )
                fecha_fuente = _parsear_fecha(actualizado_en) or datetime.fromtimestamp(
                    fuente.ruta.stat().st_mtime,
                    tz=timezone.utc,
                )
                hash_fuente = _hash_version(
                    fuente,
                    causa,
                    actualizado_en,
                    contenido,
                )
                cur.execute(
                    """
                    INSERT INTO resultados_ejecucion (
                        numero_causa, intento, estado, origen, ciudad, datos_json,
                        fuente_migracion, fuente_actualizado_en, hash_fuente
                    ) VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hash_fuente) WHERE hash_fuente IS NOT NULL DO NOTHING
                    RETURNING id
                    """,
                    (
                        causa,
                        estado,
                        origen or "MIGRACION_SQLITE",
                        fuente.ciudad,
                        Json(payload),
                        fuente.nombre,
                        fecha_fuente,
                        hash_fuente,
                    ),
                )
                if cur.fetchone() is not None:
                    insertadas += 1
                _insertar_fotografia_actual(
                    cur,
                    fuente,
                    causa,
                    estado,
                    origen or "MIGRACION_SQLITE",
                    payload,
                    fecha_fuente,
                )

            for causa, info in estados.items():
                if causa in causas_con_resultado:
                    continue
                cur.execute(
                    """
                    INSERT INTO expedientes (
                        numero_causa, ciudad, estado, reintentos,
                        origen, fuente_migracion, fuente_prioridad,
                        version_fuente_en, actualizado_en
                    ) VALUES (
                        %s, %s, %s, %s, 'MIGRACION_SQLITE', %s, %s,
                        to_timestamp(0), CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (numero_causa) DO NOTHING
                    """,
                    (
                        causa,
                        fuente.ciudad,
                        info["estado"] or "PENDIENTE",
                        info["reintentos"],
                        fuente.nombre,
                        fuente.prioridad,
                    ),
                )

            for evento_id, causa, origen, detalle, creado_en in eventos:
                hash_evento = hashlib.sha256(
                    ("%s\x1f%s\x1f%s" % (fuente.nombre, evento_id, causa)).encode("utf-8")
                ).hexdigest()
                cur.execute(
                    """
                    INSERT INTO eventos_auditoria (
                        numero_causa, tipo_evento, origen, detalle,
                        hash_fuente, creado_en
                    ) VALUES (%s, 'MIGRACION_EVENTO', %s, %s, %s, %s)
                    ON CONFLICT (hash_fuente) WHERE hash_fuente IS NOT NULL DO NOTHING
                    """,
                    (causa, origen, detalle, hash_evento, _parsear_fecha(creado_en)),
                )
    return {"insertadas": insertadas, "invalidas": invalidas}


def migrar_todo(fuentes=FUENTES_PREDETERMINADAS):
    repo = RepositorioColaPostgres.desde_config({})
    if not repo.verificar_conexion() or not repo.verificar_esquema():
        raise RuntimeError("POSTGRES_NO_INICIALIZADO")
    resultados = {}
    for fuente in fuentes:
        resultados[fuente.nombre] = migrar_fuente(repo, fuente)
        print("[OK] %s: %s" % (fuente.nombre, resultados[fuente.nombre]))
    return resultados


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribe en PostgreSQL. Sin esta opcion solo inspecciona.",
    )
    args = parser.parse_args(argv)
    resumen = inspeccionar_fuentes()
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    if resumen["faltantes"]:
        raise SystemExit("FUENTES_SQLITE_FALTANTES")
    if resumen["json_invalidos"]:
        raise SystemExit("JSON_INVALIDOS_EN_MIGRACION")
    if not args.apply:
        print("[DRY-RUN] No se escribieron datos. Use --apply despues de revisar.")
        return
    migrar_todo()
    print("[OK] Migracion idempotente finalizada.")


if __name__ == "__main__":
    main()
