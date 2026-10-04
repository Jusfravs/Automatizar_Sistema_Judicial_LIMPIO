# src/db_postgres.py
import os
import json
import logging
import psycopg2
from psycopg2.extras import execute_values, Json, RealDictCursor
from contextlib import contextmanager
from datetime import datetime
from src.catalogo_procesal import enriquecer_datos_procesales

logger = logging.getLogger("GestorPostgres")

class GestorPostgres:
    """
    Gestor de persistencia relacional nativo en PostgreSQL para casos judiciales,
    actuaciones procesales y auditoría.
    """
    def __init__(self, host=None, port=None, user=None, password=None, dbname=None):
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = int(port or os.getenv("POSTGRES_PORT", 5432))
        self.user = user or os.getenv("POSTGRES_USER", "judicial_app")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "")
        self.dbname = dbname or os.getenv("POSTGRES_DB", "casos_judiciales")

    def _get_connection(self):
        opciones_tls = {}
        if os.getenv("POSTGRES_SSLMODE"):
            opciones_tls["sslmode"] = os.environ["POSTGRES_SSLMODE"]
        if os.getenv("POSTGRES_SSLROOTCERT"):
            opciones_tls["sslrootcert"] = os.environ["POSTGRES_SSLROOTCERT"]
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.dbname,
            connect_timeout=10,
            **opciones_tls,
        )

    @contextmanager
    def _connection(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def registrar_resultado(self, numero_causa, resultado, origen="ESATJE_TRANSACCIONAL", ciudad="QUITO"):
        """
        Guarda o actualiza un expediente procesado y sus actuaciones individuales en PostgreSQL.
        """
        estado = resultado.get("estado", "PROCESADO")
        datos = dict(resultado.get("datos") or {})
        enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
        resultado = {**resultado, "datos": datos}
        actuaciones = datos.get("HISTORIAL_ACTUACIONES") or []

        ultima_etapa = datos.get("ULTIMA ETAPA") or datos.get("ETAPA_PROCESAL")
        ultima_fase = datos.get("ULTIMA FASE") or datos.get("FASE_ACTUAL")
        fecha_fin = datos.get("FECHA FIN ULTIMA FASE") or datos.get("FECHA INICIAL FASE ACTUAL")
        etapa_act = datos.get("ETAPA ACTUAL") or datos.get("SIGUIENTE_ETAPA")
        fase_act = datos.get("FASE ACTUAL") or datos.get("SIGUIENTE_FASE")
        fecha_ini_act = datos.get("FECHA INICIO FASE ACTUAL") or fecha_fin
        eta_id_ultima = datos.get("eta_id ULTIMA ETAPA")
        fas_id_ultima = datos.get("fas_id ULTIMA FASE")
        eta_id_actual = datos.get("eta_id ETAPA ACTUAL")
        fas_id_actual = datos.get("fas_id FASE ACTUAL")
        msg_esp = datos.get("COMENTARIO_ULTIMO") or datos.get("MENSAJE_ESPECIAL")
        
        actor = datos.get("ACTOR") or datos.get("DEMANDANTE")
        demandado = datos.get("DEMANDADO")
        tipo_accion = datos.get("ACCION/INFRACCION") or datos.get("TIPO_ACCION")
        fecha_inicio_j = datos.get("FECHA INICIO JUICIO") or datos.get("FECHA_INGRESO")
        ruta_html = resultado.get("ruta_html")

        with self._connection() as conn:
            with conn.cursor() as cur:
                upsert_query = """
                INSERT INTO expedientes (
                    numero_causa, ciudad, estado,
                    eta_id_ultima_etapa, ultima_etapa,
                    fas_id_ultima_fase, ultima_fase,
                    fecha_fin_ultima_fase,
                    eta_id_etapa_actual, etapa_actual,
                    fas_id_fase_actual, fase_actual, fecha_inicio_fase_actual,
                    mensaje_especial, actor, demandado, tipo_accion, fecha_inicio_juicio,
                    total_actuaciones, origen, ruta_html, datos_json, actualizado_en
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
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
                    ruta_html = COALESCE(EXCLUDED.ruta_html, expedientes.ruta_html),
                    datos_json = EXCLUDED.datos_json,
                    actualizado_en = CURRENT_TIMESTAMP;
                """
                cur.execute(upsert_query, (
                    numero_causa, ciudad, estado,
                    eta_id_ultima, ultima_etapa,
                    fas_id_ultima, ultima_fase,
                    str(fecha_fin) if fecha_fin else None,
                    eta_id_actual, etapa_act,
                    fas_id_actual, fase_act,
                    str(fecha_ini_act) if fecha_ini_act else None,
                    msg_esp, actor, demandado, tipo_accion,
                    str(fecha_inicio_j) if fecha_inicio_j else None,
                    len(actuaciones), origen, ruta_html, Json(resultado)
                ))

                # Reemplazar actuaciones de esta causa
                if actuaciones:
                    cur.execute("DELETE FROM actuaciones WHERE numero_causa = %s", (numero_causa,))
                    act_values = [
                        (
                            numero_causa,
                            str(a.get("fecha") or ""),
                            a.get("actuacion") or a.get("tipo") or "",
                            a.get("detalle") or "",
                            a.get("instancia") or "PRIMERA INSTANCIA",
                            idx + 1
                        )
                        for idx, a in enumerate(actuaciones)
                    ]
                    insert_acts = """
                    INSERT INTO actuaciones (numero_causa, fecha, tipo_actuacion, detalle, instancia, orden)
                    VALUES %s
                    """
                    execute_values(cur, insert_acts, act_values)

        logger.info("[PG_SAVE] Expediente %s persistido en PostgreSQL.", numero_causa)
        return True

    def registrar_error(self, numero_causa, origen, error_detalle):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                INSERT INTO expedientes (numero_causa, estado, origen, mensaje_especial, reintentos, actualizado_en)
                VALUES (%s, 'ERROR', %s, %s, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (numero_causa) DO UPDATE SET
                    estado = 'ERROR',
                    mensaje_especial = EXCLUDED.mensaje_especial,
                    reintentos = expedientes.reintentos + 1,
                    actualizado_en = CURRENT_TIMESTAMP;
                """, (numero_causa, origen, str(error_detalle)[:250]))

                cur.execute("""
                INSERT INTO eventos_auditoria (numero_causa, tipo_evento, origen, detalle)
                VALUES (%s, 'ERROR_EXTRACCION', %s, %s)
                """, (numero_causa, origen, str(error_detalle)))

    def obtener_resumen_fases(self):
        with self._connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM v_resumen_fases;")
                return cur.fetchall()

    def obtener_casos_revision_manual(self):
        with self._connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM v_casos_revision_manual;")
                return cur.fetchall()
