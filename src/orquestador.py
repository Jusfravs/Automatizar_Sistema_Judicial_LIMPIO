# src/orquestador.py
import json
import os
import sys
import random
import tempfile
import time
import pandas as pd

from src.antigravity_adapter import extraer_y_normalizar_dict
from src.gestor_cola import GestorCola
from src.agente_explorador import AgenteExplorador
from src.agente_extractor import AgenteExtractor
from src.gestor_estado import GestorEstado
from src.logger_config import obtener_logger

logger = obtener_logger("Orquestador")


class Orquestador:
    """
    Motor de Orquestación Principal Multi-Agente con Arquitectura de Ejecución Dual.
    Coordina:
    - Ruta Principal: Intercepción de Red API -> Limpieza Pandas -> Persistencia SQLite.
    - Ruta de Respaldo: Sincronización DOM con Freno Explícito -> BeautifulSoup4 + lxml.
    Garantiza la integridad transaccional de los 4,017 registros en SQLite.
    """
    def __init__(
        self,
        ruta_db="estado_casos.db",
        dir_temp="temp_htmls",
        ruta_json="datos_extraidos.json",
        modo_visible=False,
        patrones_api=None,
    ):
        self.ruta_json = ruta_json
        self.gestor_cola = GestorCola(ruta_db=ruta_db)
        self.agente_explorador = AgenteExplorador(
            dir_temp=dir_temp,
            modo_visible=modo_visible,
            patrones_api=patrones_api,
        )
        self.agente_extractor = AgenteExtractor()
        self.gestor_estado = GestorEstado()

    def cargar_datos_iniciales(self, ruta_origen):
        """
        Lee el archivo fuente con los 4,017 registros e inyecta la cola en SQLite de forma atómica.
        """
        logger.info(f"Cargando datos iniciales desde: {ruta_origen}")
        if not os.path.exists(ruta_origen):
            logger.error(f"No se encontró el archivo fuente: {ruta_origen}")
            return False

        try:
            if ruta_origen.endswith(".csv"):
                df = pd.read_csv(ruta_origen, low_memory=False)
            elif ruta_origen.endswith((".xlsx", ".xls")):
                df = pd.read_excel(ruta_origen)
            else:
                raise ValueError("Formato de archivo no soportado. Debe ser .csv o .xlsx")

            self.gestor_cola.poblar_cola(df)
            logger.info("Datos iniciales poblados con éxito en la cola SQLite.")
            return True
        except Exception as e:
            logger.error(f"Error al cargar datos iniciales: {e}")
            return False

    def guardar_resultado_json(self, registro_datos):
        """
        Anexa el diccionario de datos extraídos al archivo local datos_extraidos.json.
        """
        resultados = []
        if os.path.exists(self.ruta_json):
            try:
                with open(self.ruta_json, "r", encoding="utf-8") as f:
                    resultados = json.load(f)
                if not isinstance(resultados, list):
                    raise ValueError("El archivo de resultados debe contener una lista JSON.")
            except Exception as error:
                logger.warning(
                    "No se pudo leer el JSON de resultados '%s'; se iniciará uno nuevo: %s",
                    self.ruta_json,
                    error,
                )
                resultados = []

        resultados.append(registro_datos)

        directorio_salida = os.path.dirname(os.path.abspath(self.ruta_json))
        os.makedirs(directorio_salida, exist_ok=True)
        descriptor, ruta_temporal = tempfile.mkstemp(
            dir=directorio_salida,
            prefix=f".{os.path.basename(self.ruta_json)}.",
            suffix=".tmp",
        )

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as archivo_temporal:
                json.dump(resultados, archivo_temporal, ensure_ascii=False, indent=2)
                archivo_temporal.flush()
                os.fsync(archivo_temporal.fileno())

            os.replace(ruta_temporal, self.ruta_json)
        except Exception:
            if os.path.exists(ruta_temporal):
                os.unlink(ruta_temporal)
            raise

    def iniciar_procesamiento(self, limite_lote=None, max_reintentos=3):
        with self.gestor_cola.bloquear_ejecucion():
            return self._iniciar_procesamiento_bloqueado(
                limite_lote=limite_lote,
                max_reintentos=max_reintentos,
            )

    def _iniciar_procesamiento_bloqueado(self, limite_lote=None, max_reintentos=3):
        """
        Motor de ejecución central con procesamiento dual:
        - Intercepción API (Ruta Principal + Pandas)
        - Sincronización DOM (Ruta Respaldo + BeautifulSoup4)
        """
        # Verificar esquema de la base de datos antes de iniciar
        if not self.gestor_cola.verificar_esquema():
            logger.critical(
                "El esquema de la base de datos no es válido. "
                "Ejecute 'python migracion_db.py' para reparar."
            )
            return

        # Recuperar registros huérfanos (EN_PROCESO → PENDIENTE)
        huerfanos = self.gestor_cola.recuperar_huerfanos()
        if huerfanos > 0:
            logger.info("Se recuperaron %s registros huérfanos al inicio.", huerfanos)

        logger.info("Iniciando motor de ejecución multi-agente en producción...")
        procesados_lote = 0
        fallos_por_causa = {}

        try:
            while True:
                if limite_lote is not None and procesados_lote >= limite_lote:
                    logger.info("Límite de lote alcanzado (%s registros). Deteniendo orquestación.", limite_lote)
                    break

                # 1. Obtener siguiente causa pendiente desde la cola SQLite
                numero_causa = self.gestor_cola.obtener_siguiente()
                if not numero_causa:
                    filas_reiniciadas = self.gestor_cola.reiniciar_errores(max_reintentos=max_reintentos)
                    if filas_reiniciadas > 0:
                        logger.info(f"[REINTENTO] Reiniciando ciclo para {filas_reiniciadas} causa(s) fallida(s)...")
                        continue
                    else:
                        logger.info("No hay causas pendientes ni errores pendientes de reintento. Procesamiento finalizado.")
                        break

                logger.info("Procesando causa #%s: %s", procesados_lote + 1, numero_causa)

                # 2. Intentar ruta primaria con antigravity_cli (XHR/JSON + normalización).
                datos_extraidos = extraer_y_normalizar_dict(numero_causa)
                origen_resultado = None
                ruta_html = None

                if datos_extraidos is not None:
                    logger.info("[RUTA PRIMARIA] antigravity_cli extrajo datos estructurados para causa %s.", numero_causa)
                    origen_resultado = "ANTIGRAVITY_XHR"
                else:
                    logger.warning("[RUTA PRIMARIA FALLIDA] antigravity_cli no devolvió datos para causa %s.", numero_causa)

                    # 3. Ruta de respaldo DOM existente
                    ruta_html = self.agente_explorador.descargar_html_juicio(numero_causa)
                    if ruta_html and os.path.exists(ruta_html):
                        datos_extraidos = self.agente_extractor.procesar_archivo_html(ruta_html)
                        datos_extraidos["NUMERO_JUICIO"] = numero_causa
                        datos_extraidos["ORIGEN_DATA"] = "DOM_BS4"
                        origen_resultado = "DOM_BS4"
                    else:
                        intentos_fallidos = fallos_por_causa.get(numero_causa, 0) + 1
                        fallos_por_causa[numero_causa] = intentos_fallidos
                        logger.warning(
                            "Fallaron la ruta primaria antigravity_cli y la ruta de respaldo DOM para la causa %s. Registrando 'ERROR'.",
                            numero_causa,
                        )
                        self.gestor_cola.actualizar_estado(numero_causa, "ERROR")
                        retraso_minimo = 2 ** intentos_fallidos
                        retraso = random.uniform(retraso_minimo, retraso_minimo * 2)
                        logger.warning(
                            "Intento fallido %s para la causa %s; reintento tras backoff de %.2fs.",
                            intentos_fallidos,
                            numero_causa,
                            retraso,
                        )
                        time.sleep(retraso)
                        continue

                # 4. Resultado y reserva de cola se confirman juntos en SQLite.
                self.gestor_cola.registrar_resultado_transaccional(
                    numero_causa,
                    datos_extraidos,
                    origen_resultado,
                    ruta_html=ruta_html,
                )

                # 5. Persistencia local atómica para la generación posterior de reportes.
                self.guardar_resultado_json(datos_extraidos)
                fallos_por_causa.pop(numero_causa, None)
                logger.info("[OK] Causa %s guardada transaccionalmente en SQLite (%s).", numero_causa, origen_resultado)

                procesados_lote += 1

                retraso = random.uniform(2.0, 4.0)
                logger.info("Esperando %.2fs para evitar rate-limiting...", retraso)
                time.sleep(retraso)

        except KeyboardInterrupt:
            logger.warning("Ejecución interrumpida por el usuario.")
        finally:
            self.agente_explorador.cerrar()
            logger.info("Agente Explorador cerrado.")

            # 7. Compilación del reporte final con GestorEstado
            logger.info("Generando reporte tabular final...")
            self.gestor_estado.generar_reporte_final(self.ruta_json, "data/reporte_trabajo_final.csv")
            logger.info("Orquestación completada.")


if __name__ == "__main__":
    logger.info("=== MOTOR ORQUESTADOR MULTI-AGENTE (E-SATJE) ===")

    ruta_fuente = "data/reporte_trabajo.csv"
    if not os.path.exists(ruta_fuente):
        ruta_excel_fuente = os.path.join("data", "REPORTE JUICIOS PARA REVISIÓN JULIO.xlsx")
        if os.path.exists(ruta_excel_fuente):
            ruta_fuente = ruta_excel_fuente

    orquestador = Orquestador(modo_visible=False)

    stats = orquestador.gestor_cola.obtener_estadisticas()
    if not stats or stats.get("PENDIENTE", 0) == 0:
        orquestador.cargar_datos_iniciales(ruta_fuente)

    limite = int(sys.argv[1]) if len(sys.argv) > 1 else None
    orquestador.iniciar_procesamiento(limite_lote=limite)
