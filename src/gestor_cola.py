# src/gestor_cola.py
import json
import os
import sqlite3
from contextlib import contextmanager
import pandas as pd
from src.catalogo_procesal import enriquecer_datos_procesales
from src.logger_config import obtener_logger
from src.ultima_gestion import enriquecer_ultima_gestion_judicial
from src.historial_ia import inicializar_esquema, registrar_historial

logger = obtener_logger("GestorCola")


class GestorCola:
    """
    Motor de Estado y Cola de Tareas en SQLite para desacoplar el flujo de ejecución.
    """
    def __init__(self, ruta_db="estado_casos.db"):
        self.ruta_db = ruta_db
        self._inicializar_tabla()

    def _get_connection(self):
        """Devuelve una nueva conexión a SQLite con timeout de 30s."""
        return sqlite3.connect(self.ruta_db, timeout=30.0)

    @contextmanager
    def _connection(self):
        """Gestiona una conexión SQLite con rollback automático ante excepciones."""
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _exclusive_transaction(self):
        """
        Abre una conexión en modo autocommit (isolation_level=None) y emite
        BEGIN IMMEDIATE manualmente para garantizar exclusividad sin conflicto
        con el context manager de _connection.
        """
        conn = sqlite3.connect(self.ruta_db, timeout=30.0, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            # BEGIN IMMEDIATE también puede fallar (por ejemplo, si SQLite
            # permanece bloqueado). No intente revertir una transacción que no
            # llegó a existir porque ocultaría la excepción original.
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def bloquear_ejecucion(self):
        """Impide dos orquestadores simultáneos sobre la misma base SQLite."""
        ruta_bloqueo = os.path.abspath("%s.rpa.lock" % self.ruta_db)
        directorio = os.path.dirname(ruta_bloqueo)
        if directorio:
            os.makedirs(directorio, exist_ok=True)

        archivo = open(ruta_bloqueo, "a+b")
        adquirido = False
        desbloquear = None
        try:
            archivo.seek(0, os.SEEK_END)
            if archivo.tell() == 0:
                archivo.write(b"\0")
                archivo.flush()
            archivo.seek(0)

            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)

                    def desbloquear():
                        archivo.seek(0)
                        msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    def desbloquear():
                        fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                raise RuntimeError(
                    "OTRA_EJECUCION_ACTIVA:%s" % os.path.abspath(self.ruta_db)
                ) from exc

            adquirido = True
            logger.info("Bloqueo exclusivo adquirido para %s.", self.ruta_db)
            yield
        finally:
            if adquirido and desbloquear is not None:
                try:
                    desbloquear()
                except OSError:
                    logger.exception(
                        "No se pudo liberar limpiamente el bloqueo de %s.",
                        self.ruta_db,
                    )
            archivo.close()

    def _inicializar_tabla(self):
        """Crea las tablas de reserva, resultados y auditoría si no existen."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS juicios (
                    numero_causa TEXT PRIMARY KEY,
                    estado TEXT DEFAULT 'PENDIENTE',
                    ruta_html TEXT NULL,
                    reintentos INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resultados_expediente (
                    numero_causa TEXT PRIMARY KEY,
                    origen TEXT NOT NULL,
                    datos_json TEXT NOT NULL,
                    ruta_html TEXT NULL,
                    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (numero_causa) REFERENCES juicios(numero_causa)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS eventos_extraccion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_causa TEXT NOT NULL,
                    origen TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (numero_causa) REFERENCES juicios(numero_causa)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_juicios_estado ON juicios(estado)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_resultados_causa ON resultados_expediente(numero_causa)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_eventos_causa ON eventos_extraccion(numero_causa)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_eventos_creado ON eventos_extraccion(creado_en)")
            inicializar_esquema(conn)
            conn.commit()

    def poblar_cola(self, df_o_lista):
        """
        Inserta masivamente registros en la tabla juicios con INSERT OR IGNORE
        para evitar duplicar registros existentes.
        Acepta un DataFrame de Pandas o una lista de números de causa.
        """
        if isinstance(df_o_lista, pd.DataFrame):
            col_causa = 'NUMERO_JUICIO' if 'NUMERO_JUICIO' in df_o_lista.columns else df_o_lista.columns[0]
            causas = df_o_lista[col_causa].dropna().astype(str).str.strip().tolist()
        elif isinstance(df_o_lista, (list, tuple)):
            causas = [str(c).strip() for c in df_o_lista if c]
        else:
            raise ValueError("El parámetro 'df_o_lista' debe ser un DataFrame de Pandas o una lista.")

        registros = [(c,) for c in causas if c]

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO juicios (numero_causa, estado, reintentos) VALUES (?, 'PENDIENTE', 0)",
                registros
            )
            conn.commit()
            logger.info("Cola poblada/actualizada. Total de causas procesadas en inserción: %s", len(registros))

    def filtrar_causas_pendientes(self, causas):
        """Conserva causas PENDIENTE o todavía ausentes de SQLite, respetando el orden."""
        causas = [str(causa).strip() for causa in causas if causa]
        with self._connection() as conn:
            estados = {
                numero: estado
                for numero, estado in conn.execute(
                    "SELECT numero_causa, estado FROM juicios"
                )
            }
        resultado = []
        vistos = set()
        for causa in causas:
            if causa not in vistos and estados.get(causa) in (None, "PENDIENTE"):
                vistos.add(causa)
                resultado.append(causa)
        return resultado

    def obtener_siguiente(self):
        """
        Método transaccional atómico:
        Obtiene la primera causa con estado 'PENDIENTE' y actualiza su estado a 'EN_PROCESO'.
        Retorna el numero_causa o None si no hay causas pendientes.
        """
        with self._exclusive_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT numero_causa FROM juicios "
                "WHERE estado = 'PENDIENTE' ORDER BY rowid LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                return None

            numero_causa = row[0]
            cursor.execute(
                "UPDATE juicios SET estado = 'EN_PROCESO' "
                "WHERE numero_causa = ? AND estado = 'PENDIENTE'",
                (numero_causa,)
            )
            if cursor.rowcount != 1:
                logger.warning("No se pudo reservar atómicamente la causa '%s'.", numero_causa)
                raise RuntimeError(f"Fallo en la reserva atómica de '{numero_causa}'.")

            return numero_causa

    def reservar_causa(self, numero_causa, permitir_reproceso=False):
        """
        Reserva atómicamente una causa concreta antes de procesarla.

        El flujo normal solo puede reservar registros PENDIENTE. Los modos de
        reproceso explícito pueden tomar un estado terminal, pero nunca una
        causa que otra ejecución ya mantenga EN_PROCESO.
        """
        causa_str = str(numero_causa).strip()
        if not causa_str:
            raise ValueError("NUMERO_CAUSA_INVALIDO")

        with self._exclusive_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT estado FROM juicios WHERE numero_causa = ?",
                (causa_str,),
            )
            fila = cursor.fetchone()
            if fila is None:
                raise LookupError("No existe una reserva para la causa '%s'." % causa_str)

            estado_anterior = fila[0]
            if estado_anterior == "EN_PROCESO":
                raise RuntimeError("CAUSA_YA_EN_PROCESO:%s" % causa_str)
            if not permitir_reproceso and estado_anterior != "PENDIENTE":
                raise RuntimeError(
                    "CAUSA_NO_PENDIENTE:%s:%s" % (causa_str, estado_anterior)
                )

            cursor.execute(
                "UPDATE juicios SET estado = 'EN_PROCESO' "
                "WHERE numero_causa = ? AND estado = ?",
                (causa_str, estado_anterior),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("RESERVA_ATOMICA_FALLIDA:%s" % causa_str)

        logger.info(
            "Causa '%s' reservada: %s -> EN_PROCESO.",
            causa_str,
            estado_anterior,
        )
        return estado_anterior

    def actualizar_estado(self, numero_causa, nuevo_estado, ruta_html=None):
        """
        Actualiza el estado de una causa y opcionalmente su ruta_html.
        """
        causa_str = str(numero_causa).strip()
        with self._connection() as conn:
            cursor = conn.cursor()
            if ruta_html is not None:
                cursor.execute(
                    "UPDATE juicios SET estado = ?, ruta_html = ? WHERE numero_causa = ?",
                    (nuevo_estado, ruta_html, causa_str)
                )
            else:
                cursor.execute(
                    "UPDATE juicios SET estado = ? WHERE numero_causa = ?",
                    (nuevo_estado, causa_str)
                )
            conn.commit()

    def registrar_resultado_transaccional(
        self, numero_causa, resultado, origen, ruta_html=None, estado_final="PROCESADO"
    ):
        """
        Persiste el resultado del expediente y su estado final
        en una única transacción SQLite con BEGIN IMMEDIATE.
        """
        causa_str = str(numero_causa).strip()
        if isinstance(resultado, dict):
            resultado = dict(resultado)
            if isinstance(resultado.get("datos"), dict):
                datos = dict(resultado["datos"])
                enriquecer_datos_procesales(datos, normalizar_etiquetas=True)
                enriquecer_ultima_gestion_judicial(datos)
                resultado["datos"] = datos
            else:
                enriquecer_datos_procesales(
                    resultado, normalizar_etiquetas=True
                )
                enriquecer_ultima_gestion_judicial(resultado)
        datos_json = json.dumps(resultado, ensure_ascii=False)
        estados_validos = {
            "PROCESADO", "PARCIAL", "SIN_RESULTADOS", "ERROR",
            "EXCLUIDO_NO_CORRESPONDE",
        }
        if estado_final not in estados_validos:
            raise ValueError("Estado final SQLite no permitido: %s" % estado_final)

        with self._exclusive_transaction() as conn:
            cursor = conn.cursor()
            conservar_evidencia_previa = False
            if estado_final == "ERROR" and not self._resultado_tiene_evidencia(resultado):
                cursor.execute(
                    "SELECT datos_json FROM resultados_expediente WHERE numero_causa = ?",
                    (causa_str,),
                )
                fila_previa = cursor.fetchone()
                if fila_previa:
                    try:
                        resultado_previo = json.loads(fila_previa[0])
                    except (TypeError, json.JSONDecodeError):
                        logger.warning(
                            "Resultado previo no v\u00e1lido para %s; se reemplazar\u00e1 con el error actual.",
                            causa_str,
                        )
                    else:
                        conservar_evidencia_previa = self._resultado_tiene_evidencia(
                            resultado_previo
                        )

            if conservar_evidencia_previa:
                logger.warning(
                    "Se conserva la evidencia previa de %s ante un error sin datos nuevos.",
                    causa_str,
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO resultados_expediente (numero_causa, origen, datos_json, ruta_html)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(numero_causa) DO UPDATE SET
                        origen = excluded.origen,
                        datos_json = excluded.datos_json,
                        ruta_html = COALESCE(excluded.ruta_html, resultados_expediente.ruta_html),
                        actualizado_en = CURRENT_TIMESTAMP
                    """,
                    (causa_str, origen, datos_json, ruta_html),
                )
            cursor.execute(
                "UPDATE juicios SET estado = ?, ruta_html = COALESCE(?, ruta_html) WHERE numero_causa = ?",
                (estado_final, ruta_html, causa_str),
            )
            if cursor.rowcount != 1:
                raise LookupError("No existe una reserva para la causa '%s'." % causa_str)
            if not conservar_evidencia_previa and isinstance(resultado, dict):
                registrar_historial(conn, causa_str, resultado)

    @staticmethod
    def _resultado_tiene_evidencia(resultado):
        """Indica si un resultado conserva evidencia procesal reutilizable."""
        if not isinstance(resultado, dict):
            return False
        datos = resultado.get("datos")
        if not isinstance(datos, dict):
            return False
        if datos.get("HISTORIAL_ACTUACIONES"):
            return True
        return any(
            datos.get(campo)
            for campo in (
                "ULTIMA ETAPA",
                "ULTIMA FASE",
                "FECHA FIN ULTIMA FASE",
                "ETAPA_PROCESAL",
                "FASE_PROCESAL",
            )
        )

    def registrar_error_extraccion(self, numero_causa, origen, detalle):
        """Registra fallos de captura sin cancelar la ruta de respaldo DOM."""
        causa_str = str(numero_causa).strip()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO eventos_extraccion (numero_causa, origen, detalle)
                VALUES (?, ?, ?)
                """,
                (causa_str, origen, str(detalle)),
            )
            conn.commit()

    def obtener_estadisticas(self):
        """Retorna un diccionario con el conteo de registros agrupados por estado."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT estado, COUNT(*) FROM juicios GROUP BY estado")
            rows = cursor.fetchall()
            return dict(rows)

    def reiniciar_errores(self, max_reintentos=3):
        """
        Cambia el estado de 'ERROR' a 'PENDIENTE' e incrementa en 1 la columna 'reintentos'
        para todos los registros con reintentos < max_reintentos.
        Retorna la cantidad de filas modificadas.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE juicios
                SET estado = 'PENDIENTE', reintentos = reintentos + 1
                WHERE estado = 'ERROR' AND reintentos < ?
                """,
                (max_reintentos,)
            )
            conn.commit()
            filas_modificadas = cursor.rowcount
            if filas_modificadas > 0:
                logger.info("Reiniciados %s registros de 'ERROR' a 'PENDIENTE'.", filas_modificadas)
            return filas_modificadas

    def recuperar_huerfanos(self):
        """
        Recupera registros que quedaron atrapados en estado 'EN_PROCESO'
        (por ejemplo, tras una interrupción inesperada del proceso).
        Los devuelve a 'PENDIENTE' e incrementa su contador de reintentos.
        Registra un evento de recuperación en eventos_extraccion.
        Retorna la cantidad de registros recuperados.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            # Identificar huérfanos
            cursor.execute(
                "SELECT numero_causa FROM juicios WHERE estado = 'EN_PROCESO'"
            )
            huerfanos = cursor.fetchall()

            if not huerfanos:
                return 0

            # Recuperar a PENDIENTE
            cursor.execute(
                """
                UPDATE juicios
                SET estado = 'PENDIENTE', reintentos = reintentos + 1
                WHERE estado = 'EN_PROCESO'
                """
            )
            filas = cursor.rowcount

            # Registrar evento de recuperación
            for (causa,) in huerfanos:
                cursor.execute(
                    """
                    INSERT INTO eventos_extraccion (numero_causa, origen, detalle)
                    VALUES (?, 'RECUPERACION', 'Registro huérfano EN_PROCESO recuperado a PENDIENTE al inicio del proceso.')
                    """,
                    (causa,)
                )

            conn.commit()
            logger.info(
                "Recuperados %s registros huérfanos de 'EN_PROCESO' a 'PENDIENTE': %s",
                filas,
                [c[0] for c in huerfanos]
            )
            return filas

    def verificar_esquema(self):
        """
        Verifica que las tres tablas requeridas existen en la base de datos.
        Retorna True si el esquema es válido, False en caso contrario.
        """
        tablas_requeridas = ["juicios", "resultados_expediente", "eventos_extraccion"]
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas_existentes = {row[0] for row in cursor.fetchall()}

        faltantes = [t for t in tablas_requeridas if t not in tablas_existentes]
        if faltantes:
            logger.error("Tablas faltantes en la base de datos: %s", faltantes)
            return False

        logger.info("Esquema de base de datos verificado correctamente.")
        return True
