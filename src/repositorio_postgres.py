"""Repositorio PostgreSQL para cola concurrente y resultados judiciales."""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterable, Mapping

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values

from src.catalogo_procesal import enriquecer_datos_procesales
from src.ejecucion import ESTADOS_TERMINALES, TrabajoCola
from src.ultima_gestion import enriquecer_ultima_gestion_judicial
from src.historial_ia import (
    VERSION_ESQUEMA, huella_contexto, normalizar_actuaciones,
)


logger = logging.getLogger("RepositorioPostgres")


class RepositorioColaPostgres:
    """Fuente de verdad para ejecuciones con uno o mas trabajadores."""

    def __init__(self, host, port, user, password, dbname, connect_timeout=10,
                 sslmode=None, sslrootcert=None):
        self.host = host or "localhost"
        self.port = int(port or 5432)
        self.user = user or "judicial_app"
        self.password = password or ""
        self.dbname = dbname or "casos_judiciales"
        self.connect_timeout = int(connect_timeout)
        self.sslmode = sslmode
        self.sslrootcert = sslrootcert

    @classmethod
    def desde_config(cls, config: Mapping[str, Any] | None):
        valores = dict(config or {})
        variable_password = valores.get("password_env", "POSTGRES_PASSWORD")
        return cls(
            host=valores.get("host", os.getenv("POSTGRES_HOST", "localhost")),
            port=valores.get("puerto", os.getenv("POSTGRES_PORT", 5432)),
            user=valores.get("usuario", os.getenv("POSTGRES_USER", "judicial_app")),
            password=os.getenv(variable_password, ""),
            dbname=valores.get("nombre_db", os.getenv("POSTGRES_DB", "casos_judiciales")),
            connect_timeout=valores.get("connect_timeout", 10),
            sslmode=valores.get("sslmode", os.getenv("POSTGRES_SSLMODE")),
            sslrootcert=valores.get("sslrootcert", os.getenv("POSTGRES_SSLROOTCERT")),
        )

    def _get_connection(self):
        opciones_tls = {}
        if self.sslmode:
            opciones_tls["sslmode"] = self.sslmode
        if self.sslrootcert:
            opciones_tls["sslrootcert"] = self.sslrootcert
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.dbname,
            connect_timeout=self.connect_timeout,
            application_name="sistema_judicial",
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

    def verificar_conexion(self):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0] == 1

    def verificar_esquema(self):
        requeridas = {
            "ejecuciones",
            "cola_trabajo",
            "resultados_ejecucion",
            "expedientes",
            "actuaciones",
            "eventos_auditoria",
            "actuaciones_procesales",
            "ejecuciones_inferencia",
            "auditorias_ia",
            "revisiones_ia",
            "hitos_procesales",
        }
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tablename
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public' AND tablename = ANY(%s)
                    """,
                    (list(requeridas),),
                )
                existentes = {fila[0] for fila in cur.fetchall()}
        faltantes = requeridas - existentes
        if faltantes:
            logger.error("Esquema PostgreSQL incompleto: %s", sorted(faltantes))
        return not faltantes

    def verificar_auditoria_config(self):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT EXISTS (
                         SELECT 1 FROM information_schema.columns
                         WHERE table_schema = 'public' AND table_name = 'ejecuciones'
                           AND column_name = 'config_sha256'
                       )"""
                )
                return bool(cur.fetchone()[0])

    def crear_ejecucion(self, perfil, total_esperado, trabajadores, config_sha256=None):
        ejecucion_id = str(uuid.uuid4())
        with self._connection() as conn:
            with conn.cursor() as cur:
                if config_sha256 is None:
                    cur.execute(
                        """INSERT INTO ejecuciones
                           (id, perfil, estado, trabajadores_configurados, total_esperado)
                           VALUES (%s, %s, 'PREPARADA', %s, %s)""",
                        (ejecucion_id, str(perfil), int(trabajadores), int(total_esperado)),
                    )
                else:
                    cur.execute(
                        """INSERT INTO ejecuciones
                           (id, perfil, estado, trabajadores_configurados, total_esperado, config_sha256)
                           VALUES (%s, %s, 'PREPARADA', %s, %s, %s)""",
                        (ejecucion_id, str(perfil), int(trabajadores), int(total_esperado), config_sha256),
                    )
        return ejecucion_id

    def poblar_trabajos(self, ejecucion_id, causas: Iterable[str]):
        unicas = []
        vistas = set()
        for causa in causas:
            valor = str(causa or "").strip()
            if valor and valor not in vistas:
                vistas.add(valor)
                unicas.append(valor)
        if not unicas:
            return 0
        valores = [
            (ejecucion_id, causa, posicion)
            for posicion, causa in enumerate(unicas, start=1)
        ]
        with self._connection() as conn:
            with conn.cursor() as cur:
                filas_insertadas = execute_values(
                    cur,
                    """
                    INSERT INTO cola_trabajo (ejecucion_id, numero_causa, posicion)
                    VALUES %s
                    ON CONFLICT (ejecucion_id, numero_causa) DO NOTHING
                    RETURNING id
                    """,
                    valores,
                    fetch=True,
                )
                # rowcount corresponde solo a la ultima pagina de execute_values.
                insertados = len(filas_insertadas)
        return insertados

    def iniciar_ejecucion(self, ejecucion_id):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ejecuciones
                    SET estado = 'ACTIVA', iniciado_en = COALESCE(iniciado_en, CURRENT_TIMESTAMP)
                    WHERE id = %s AND estado = 'PREPARADA'
                    """,
                    (ejecucion_id,),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("EJECUCION_NO_PREPARADA:%s" % ejecucion_id)

    def reservar_siguiente(self, ejecucion_id, worker_id, lease_segundos):
        with self._connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH candidato AS (
                        SELECT id
                        FROM cola_trabajo
                        WHERE ejecucion_id = %s
                          AND estado IN ('PENDIENTE', 'ERROR_REINTENTABLE')
                          AND disponible_desde <= CURRENT_TIMESTAMP
                        ORDER BY prioridad DESC, posicion ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE cola_trabajo c
                    SET estado = 'EN_PROCESO',
                        intentos = c.intentos + 1,
                        worker_id = %s,
                        reservado_en = CURRENT_TIMESTAMP,
                        heartbeat_en = CURRENT_TIMESTAMP,
                        lease_hasta = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                        actualizado_en = CURRENT_TIMESTAMP
                    FROM candidato
                    WHERE c.id = candidato.id
                    RETURNING c.id, c.numero_causa, c.intentos, c.posicion
                    """,
                    (ejecucion_id, worker_id, int(lease_segundos)),
                )
                fila = cur.fetchone()
        if not fila:
            return None
        return TrabajoCola(
            id=fila["id"],
            numero_causa=fila["numero_causa"],
            intentos=fila["intentos"],
            posicion=fila["posicion"],
        )

    def renovar_lease(self, trabajo_id, worker_id, lease_segundos):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cola_trabajo
                    SET heartbeat_en = CURRENT_TIMESTAMP,
                        lease_hasta = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s AND worker_id = %s AND estado = 'EN_PROCESO'
                    """,
                    (int(lease_segundos), trabajo_id, worker_id),
                )
                return cur.rowcount == 1

    @staticmethod
    def _normalizar_resultado(resultado):
        payload = dict(resultado or {})
        datos = dict(payload.get("datos") or {})
        enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
        enriquecer_ultima_gestion_judicial(datos)
        payload["datos"] = datos
        return payload, datos

    @staticmethod
    def _campos_expediente(datos):
        return {
            "ultima_etapa": datos.get("ULTIMA ETAPA") or datos.get("ETAPA_PROCESAL"),
            "ultima_fase": datos.get("ULTIMA FASE") or datos.get("FASE_ACTUAL"),
            "fecha_fin": datos.get("FECHA FIN ULTIMA FASE")
            or datos.get("FECHA INICIAL FASE ACTUAL"),
            "etapa_actual": datos.get("ETAPA ACTUAL") or datos.get("SIGUIENTE_ETAPA"),
            "fase_actual": datos.get("FASE ACTUAL") or datos.get("SIGUIENTE_FASE"),
            "fecha_inicio_actual": datos.get("FECHA INICIO FASE ACTUAL")
            or datos.get("FECHA INICIAL FASE ACTUAL"),
            "mensaje": datos.get("COMENTARIO_ULTIMO") or datos.get("MENSAJE_ESPECIAL"),
            "actor": datos.get("ACTOR") or datos.get("DEMANDANTE"),
            "demandado": datos.get("DEMANDADO"),
            "tipo_accion": datos.get("ACCION/INFRACCION") or datos.get("TIPO_ACCION"),
            "fecha_inicio_juicio": datos.get("FECHA INICIO JUICIO") or datos.get("FECHA_INGRESO"),
            "eta_id_ultima": datos.get("eta_id ULTIMA ETAPA"),
            "fas_id_ultima": datos.get("fas_id ULTIMA FASE"),
            "eta_id_actual": datos.get("eta_id ETAPA ACTUAL"),
            "fas_id_actual": datos.get("fas_id FASE ACTUAL"),
        }

    def completar_trabajo(
        self, trabajo, worker_id, estado_final, resultado, origen, ciudad
    ):
        if estado_final not in ESTADOS_TERMINALES - {"ERROR_FINAL", "CANCELADO"}:
            raise ValueError("ESTADO_TERMINAL_INVALIDO:%s" % estado_final)
        payload, datos = self._normalizar_resultado(resultado)
        campos = self._campos_expediente(datos)
        actuaciones = datos.get("HISTORIAL_ACTUACIONES") or []
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ejecucion_id FROM cola_trabajo WHERE id = %s FOR UPDATE",
                    (trabajo.id,),
                )
                fila = cur.fetchone()
                if not fila:
                    raise LookupError("TRABAJO_NO_EXISTE:%s" % trabajo.id)
                ejecucion_id = fila[0]
                cur.execute(
                    """
                    INSERT INTO resultados_ejecucion (
                        ejecucion_id, trabajo_id, numero_causa, intento, estado,
                        origen, worker_id, ciudad, datos_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        ejecucion_id,
                        trabajo.id,
                        trabajo.numero_causa,
                        trabajo.intentos,
                        estado_final,
                        origen,
                        worker_id,
                        ciudad,
                        Json(payload),
                    ),
                )
                cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO expedientes (
                        numero_causa, ciudad, estado,
                        eta_id_ultima_etapa, ultima_etapa,
                        fas_id_ultima_fase, ultima_fase, fecha_fin_ultima_fase,
                        eta_id_etapa_actual, etapa_actual,
                        fas_id_fase_actual, fase_actual, fecha_inicio_fase_actual,
                        mensaje_especial, actor, demandado, tipo_accion,
                        fecha_inicio_juicio, total_actuaciones, origen,
                        reintentos, datos_json, version_fuente_en, actualizado_en
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                        reintentos = EXCLUDED.reintentos,
                        datos_json = EXCLUDED.datos_json,
                        version_fuente_en = CURRENT_TIMESTAMP,
                        actualizado_en = CURRENT_TIMESTAMP
                    """,
                    (
                        trabajo.numero_causa,
                        ciudad,
                        estado_final,
                        campos["eta_id_ultima"],
                        campos["ultima_etapa"],
                        campos["fas_id_ultima"],
                        campos["ultima_fase"],
                        str(campos["fecha_fin"]) if campos["fecha_fin"] else None,
                        campos["eta_id_actual"],
                        campos["etapa_actual"],
                        campos["fas_id_actual"],
                        campos["fase_actual"],
                        str(campos["fecha_inicio_actual"])
                        if campos["fecha_inicio_actual"]
                        else None,
                        campos["mensaje"],
                        campos["actor"],
                        campos["demandado"],
                        campos["tipo_accion"],
                        str(campos["fecha_inicio_juicio"])
                        if campos["fecha_inicio_juicio"]
                        else None,
                        len(actuaciones),
                        origen,
                        trabajo.intentos,
                        Json(payload),
                    ),
                )
                cur.execute(
                    "DELETE FROM actuaciones WHERE numero_causa = %s",
                    (trabajo.numero_causa,),
                )
                if actuaciones:
                    valores = [
                        (
                            trabajo.numero_causa,
                            str(actuacion.get("fecha") or ""),
                            actuacion.get("actuacion") or actuacion.get("tipo") or "",
                            actuacion.get("detalle") or "",
                            actuacion.get("instancia") or "PRIMERA INSTANCIA",
                            indice,
                        )
                        for indice, actuacion in enumerate(actuaciones, start=1)
                    ]
                    execute_values(
                        cur,
                        """
                        INSERT INTO actuaciones (
                            numero_causa, fecha, tipo_actuacion, detalle, instancia, orden
                        ) VALUES %s
                        """,
                        valores,
                    )
                    normalizadas = normalizar_actuaciones(
                        trabajo.numero_causa, actuaciones
                    )
                    valores_historial = [(
                        act["actuacion_id"], act["numero_causa"], act["carpeta"],
                        act["fecha"], act["titulo"], act["detalle"],
                        act["contenido_sha256"], Json(json.loads(act["datos_json"])),
                    ) for act in normalizadas]
                    if valores_historial:
                        execute_values(cur, """
                            INSERT INTO actuaciones_procesales
                            (actuacion_id, numero_causa, carpeta, fecha, titulo,
                             detalle, contenido_sha256, datos_json) VALUES %s
                            ON CONFLICT (actuacion_id) DO NOTHING
                        """, valores_historial)
                        estado_inferencia = {
                            campo: datos.get(campo) for campo in (
                                "ULTIMA ETAPA", "ULTIMA FASE", "ETAPA ACTUAL",
                                "FASE ACTUAL", "FECHA FIN ULTIMA FASE",
                                "FECHA INICIO FASE ACTUAL", "eta_id ULTIMA ETAPA",
                                "fas_id ULTIMA FASE", "eta_id ETAPA ACTUAL",
                                "fas_id FASE ACTUAL",
                            )
                        }
                        cur.execute("""
                            INSERT INTO ejecuciones_inferencia
                            (numero_causa, huella_contexto, version_reglas, estado_json)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (numero_causa, huella_contexto, version_reglas)
                            DO NOTHING
                        """, (
                            trabajo.numero_causa, huella_contexto(normalizadas, datos),
                            VERSION_ESQUEMA, Json(estado_inferencia),
                        ))
                cur.execute(
                    """
                    UPDATE cola_trabajo
                    SET estado = %s, worker_id = NULL, lease_hasta = NULL,
                        heartbeat_en = CURRENT_TIMESTAMP, ultimo_error = NULL,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s AND worker_id = %s AND estado = 'EN_PROCESO'
                    """,
                    (estado_final, trabajo.id, worker_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("LEASE_PERDIDO:%s" % trabajo.id)
                cur.execute(
                    """
                    INSERT INTO eventos_auditoria (
                        numero_causa, ejecucion_id, worker_id, tipo_evento, origen, detalle
                    ) VALUES (%s, %s, %s, 'TRABAJO_COMPLETADO', %s, %s)
                    """,
                    (
                        trabajo.numero_causa,
                        ejecucion_id,
                        worker_id,
                        origen,
                        json.dumps({"estado": estado_final}, ensure_ascii=False),
                    ),
                )

    def fallar_trabajo(
        self,
        trabajo,
        worker_id,
        detalle,
        resultado,
        recuperable,
        maximo_intentos,
    ):
        reintentable = bool(recuperable and trabajo.intentos < maximo_intentos)
        estado = "ERROR_REINTENTABLE" if reintentable else "ERROR_FINAL"
        esperas = {1: 60, 2: 300}
        espera = esperas.get(trabajo.intentos, 900)
        payload = dict(resultado or {})
        payload.setdefault("estado", "ERROR")
        payload.setdefault("error", str(detalle))
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ejecucion_id FROM cola_trabajo WHERE id = %s FOR UPDATE",
                    (trabajo.id,),
                )
                fila = cur.fetchone()
                if not fila:
                    raise LookupError("TRABAJO_NO_EXISTE:%s" % trabajo.id)
                ejecucion_id = fila[0]
                cur.execute(
                    """
                    INSERT INTO resultados_ejecucion (
                        ejecucion_id, trabajo_id, numero_causa, intento, estado,
                        origen, worker_id, datos_json
                    ) VALUES (%s, %s, %s, %s, %s, 'ESATJE_TRANSACCIONAL', %s, %s)
                    """,
                    (
                        ejecucion_id,
                        trabajo.id,
                        trabajo.numero_causa,
                        trabajo.intentos,
                        estado,
                        worker_id,
                        Json(payload),
                    ),
                )
                cur.execute(
                    """
                    UPDATE cola_trabajo
                    SET estado = %s,
                        disponible_desde = CASE
                            WHEN %s THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                            ELSE disponible_desde
                        END,
                        worker_id = NULL,
                        lease_hasta = NULL,
                        heartbeat_en = CURRENT_TIMESTAMP,
                        ultimo_error = %s,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s AND worker_id = %s AND estado = 'EN_PROCESO'
                    """,
                    (
                        estado,
                        reintentable,
                        espera,
                        str(detalle)[:4000],
                        trabajo.id,
                        worker_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("LEASE_PERDIDO:%s" % trabajo.id)
                if estado == "ERROR_FINAL":
                    cur.execute(
                        """
                        INSERT INTO expedientes (
                            numero_causa, estado, mensaje_especial, origen,
                            reintentos, actualizado_en
                        ) VALUES (%s, 'ERROR_FINAL', %s, 'ESATJE_TRANSACCIONAL', %s,
                                  CURRENT_TIMESTAMP)
                        ON CONFLICT (numero_causa) DO UPDATE SET
                            estado = 'ERROR_FINAL',
                            mensaje_especial = EXCLUDED.mensaje_especial,
                            reintentos = EXCLUDED.reintentos,
                            actualizado_en = CURRENT_TIMESTAMP
                        """,
                        (trabajo.numero_causa, str(detalle)[:255], trabajo.intentos),
                    )
                cur.execute(
                    """
                    INSERT INTO eventos_auditoria (
                        numero_causa, ejecucion_id, worker_id, tipo_evento, origen, detalle
                    ) VALUES (%s, %s, %s, %s, 'ESATJE_TRANSACCIONAL', %s)
                    """,
                    (
                        trabajo.numero_causa,
                        ejecucion_id,
                        worker_id,
                        estado,
                        str(detalle),
                    ),
                )
        return estado

    def recuperar_leases_vencidos(self, ejecucion_id, maximo_intentos):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH recuperados AS (
                        UPDATE cola_trabajo
                        SET estado = CASE
                                WHEN intentos < %s THEN 'ERROR_REINTENTABLE'
                                ELSE 'ERROR_FINAL'
                            END,
                            disponible_desde = CURRENT_TIMESTAMP,
                            worker_id = NULL,
                            lease_hasta = NULL,
                            ultimo_error = 'LEASE_VENCIDO',
                            actualizado_en = CURRENT_TIMESTAMP
                        WHERE ejecucion_id = %s
                          AND estado = 'EN_PROCESO'
                          AND lease_hasta < CURRENT_TIMESTAMP
                        RETURNING numero_causa, estado
                    )
                    INSERT INTO eventos_auditoria (
                        numero_causa, ejecucion_id, tipo_evento, origen, detalle
                    )
                    SELECT numero_causa, %s, 'LEASE_RECUPERADO', 'COORDINADOR', estado
                    FROM recuperados
                    RETURNING id
                    """,
                    (int(maximo_intentos), ejecucion_id, ejecucion_id),
                )
                return cur.rowcount

    def obtener_estadisticas(self, ejecucion_id):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT estado, COUNT(*)
                    FROM cola_trabajo
                    WHERE ejecucion_id = %s
                    GROUP BY estado
                    """,
                    (ejecucion_id,),
                )
                return {estado: total for estado, total in cur.fetchall()}

    def listar_causas_procesadas(self, perfil=None):
        """Causas terminadas en ejecuciones completas de esta base PostgreSQL."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT c.numero_causa
                    FROM cola_trabajo AS c
                    JOIN ejecuciones AS e ON e.id = c.ejecucion_id
                    WHERE c.estado = 'PROCESADO'
                      AND e.estado = 'COMPLETADA'
                      AND (%s IS NULL OR e.perfil = %s)
                    """,
                    (perfil, perfil),
                )
                return [fila[0] for fila in cur.fetchall()]

    def hay_trabajo_programado(self, ejecucion_id):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM cola_trabajo
                        WHERE ejecucion_id = %s
                          AND estado IN ('PENDIENTE', 'ERROR_REINTENTABLE')
                    )
                    """,
                    (ejecucion_id,),
                )
                return bool(cur.fetchone()[0])

    def listar_resultados(self, ejecucion_id, despues_de=0):
        with self._connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, numero_causa, estado, origen, worker_id, ciudad,
                           datos_json, creado_en
                    FROM resultados_ejecucion
                    WHERE ejecucion_id = %s AND id > %s
                    ORDER BY id
                    """,
                    (ejecucion_id, int(despues_de)),
                )
                return [dict(fila) for fila in cur.fetchall()]

    def listar_fallidos(self, ejecucion_id):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT numero_causa
                    FROM cola_trabajo
                    WHERE ejecucion_id = %s
                      AND estado IN ('ERROR_FINAL', 'REVISION')
                    ORDER BY posicion
                    """,
                    (ejecucion_id,),
                )
                return [fila[0] for fila in cur.fetchall()]

    def finalizar_ejecucion(self, ejecucion_id, estado):
        if estado not in {"COMPLETADA", "FALLIDA", "CANCELADA"}:
            raise ValueError("ESTADO_EJECUCION_INVALIDO")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ejecuciones
                    SET estado = %s, finalizado_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (estado, ejecucion_id),
                )
