import importlib
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from src.gestor_casos import GestorCasos
from src.gestor_cola import GestorCola
from src.motor_busqueda_web import BotJudicial
from scripts.reclasificar_desde_sqlite import _causas_por_sucursal


class BotonFalso:
    def __init__(self):
        self.clicks = 0

    def click(self):
        self.clicks += 1


class PaginaFalsa:
    url = "https://ejemplo.local/actuaciones"

    @staticmethod
    def is_closed():
        return False


class FrenoNavegacionTests(unittest.TestCase):
    def crear_bot(self, **navegacion):
        return BotJudicial("https://ejemplo.local", navegacion)

    def test_bloqueo_impide_click_real(self):
        bot = self.crear_bot()
        boton = BotonFalso()
        bot._bloqueo_navegacion = {
            "activo": True,
            "token": "intento:carpeta",
            "causa": "23331202202089",
        }

        with self.assertRaisesRegex(RuntimeError, "NAVEGACION_BLOQUEADA"):
            bot._click_navegacion(boton, "click_prohibido")

        self.assertEqual(boton.clicks, 0)
        self.assertEqual(len(bot._intentos_navegacion_bloqueados), 1)

    def test_ventana_api_excluye_respuestas_previas_y_otra_causa(self):
        bot = self.crear_bot()
        bot.paquetes_api_interceptados = [
            {"secuencia": 4, "url": "/api/actuaciones", "data": {"idJuicio": "23331202202089"}},
            {"secuencia": 5, "url": "/api/actuaciones", "data": {"idJuicio": "23331202202088"}},
            {"secuencia": 6, "url": "/api/actuaciones", "data": {"idJuicio": "23331202202089"}},
            {"secuencia": 7, "url": "/api/actuaciones", "data": {"idJuicio": "23331202202089"}},
        ]

        paquetes = bot._paquetes_ventana(5, 6, "23331202202089")

        self.assertEqual([paquete["secuencia"] for paquete in paquetes], [6])

    def test_extraccion_transforma_sin_pagina_ni_navegacion(self):
        bot = self.crear_bot()
        bot.page = None
        bot.extractor.procesar_html_string = lambda contenido, **kwargs: {}
        bot._aplicar_inferencia_consolidada = lambda datos, causa=None, **kwargs: datos

        datos = bot._ejecutar_extraccion_detalles(
            "23331202202089",
            paquetes_api=[{
                "data": {
                    "idJuicio": "23331202202089",
                    "actuaciones": [{"fecha": "24/02/2023", "detalle": "SENTENCIA"}],
                }
            }],
            contenido_html="<html><body></body></html>",
        )

        self.assertEqual(len(datos["HISTORIAL_ACTUACIONES"]), 1)
        self.assertEqual(datos["ORIGEN_DATA"], "API")

    def test_bloqueo_solo_se_libera_con_manifiesto_terminal(self):
        bot = self.crear_bot()
        bot.page = PaginaFalsa()
        bot._intento_actual = "intento"
        descriptor = {"clave_carpeta": "carpeta"}
        token = bot._activar_bloqueo_navegacion("23331202202089", descriptor)
        with tempfile.TemporaryDirectory() as temporal:
            manifiesto = os.path.join(temporal, "result.json")
            with open(manifiesto, "w", encoding="utf-8") as archivo:
                json.dump({"estado": "COMPLETA"}, archivo)
            bot._finalizar_bloqueo_navegacion(token, manifiesto)

        self.assertIsNone(bot._bloqueo_navegacion)

    def test_artefactos_carpeta_persisten_desde_ruta_profunda(self):
        bot = self.crear_bot()
        bot.page = PaginaFalsa()
        bot._intento_actual = "07331202500747-26870a67b248"
        causa = "07331202500747"
        descriptor = {"clave_carpeta": causa + "_1_10_12_2025_13_24_" + "x" * 60}
        resultado = {"advertencias": [], "clave_carpeta": descriptor["clave_carpeta"]}
        anterior = os.getcwd()
        with tempfile.TemporaryDirectory() as temporal:
            profundidad = max(0, 155 - len(temporal))
            directorio = os.path.join(temporal, "x" * profundidad)
            os.makedirs(directorio, exist_ok=True)
            try:
                os.chdir(directorio)
                manifiesto = bot._guardar_artefactos_carpeta(
                    causa, descriptor, [], "<html></html>", [], resultado, {}
                )
                with open(manifiesto, encoding="utf-8") as archivo:
                    guardado = json.load(archivo)
                self.assertEqual(guardado["clave_carpeta"], descriptor["clave_carpeta"])
                self.assertEqual(len(os.path.basename(os.path.dirname(manifiesto))), 18)
                if os.name == "nt":
                    self.assertLess(len(os.path.abspath(manifiesto)), 260)
            finally:
                os.chdir(anterior)

    def test_flujo_envia_busqueda_y_devuelve_contrato_sin_resultados(self):
        bot = self.crear_bot()
        llamadas = []
        bot._preparar_busqueda = lambda causa: llamadas.append("preparar") or causa
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None
        bot._activar_captcha_con_click_inicial = (
            lambda causa, intento: llamadas.append("activar_captcha")
        )
        bot._resolver_o_esperar_captcha = (
            lambda causa, intento: llamadas.append("resolver_captcha")
        )
        bot._enviar_busqueda_una_vez = (
            lambda causa, intento: llamadas.append("enviar")
        )
        bot._esperar_despues_captcha = (
            lambda causa: llamadas.append("esperar_10s")
        )
        bot._esperar_resultados = (
            lambda causa: llamadas.append("resultados") or "SIN_RESULTADOS"
        )
        bot._volver_al_buscador = lambda causa: llamadas.append("volver") or True

        resultado = bot.procesar_flujo_judicatura("23331-2022-02089")

        self.assertEqual(
            llamadas,
            [
                "preparar", "activar_captcha", "resolver_captcha", "esperar_10s",
                "enviar", "resultados", "volver",
            ],
        )
        self.assertEqual(resultado["estado"], "SIN_RESULTADOS")
        self.assertTrue(resultado["regreso_confirmado"])

    def test_flujo_marca_notificacion_sin_resultados_para_revision_manual(self):
        bot = self.crear_bot()
        llamadas = []
        bot._preparar_busqueda = lambda causa: llamadas.append("preparar") or causa
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None
        bot._activar_captcha_con_click_inicial = (
            lambda causa, intento: llamadas.append("activar_captcha")
        )
        bot._resolver_o_esperar_captcha = (
            lambda causa, intento: llamadas.append("resolver_captcha")
        )
        bot._enviar_busqueda_una_vez = (
            lambda causa, intento: llamadas.append("enviar")
        )
        bot._esperar_despues_captcha = (
            lambda causa: llamadas.append("esperar_10s")
        )
        bot._esperar_resultados = lambda causa: (
            llamadas.append("resultados")
            or "VERIFICACION_MANUAL_SIN_RESULTADOS"
        )
        bot._volver_al_buscador = lambda causa: llamadas.append("volver") or True

        resultado = bot.procesar_flujo_judicatura("12331-2016-1181")

        self.assertEqual(resultado["estado"], "ERROR_VERIFICACION_MANUAL")
        self.assertEqual(
            resultado["error"],
            "Verificar manualmente (La consulta no devolvi\u00f3 resultados)",
        )
        self.assertFalse(resultado["requiere_reintento"])
        self.assertTrue(resultado["regreso_confirmado"])
        self.assertEqual(llamadas.count("resultados"), 1)

    def test_busqueda_rechazada_reintenta_sin_doble_click(self):
        bot = self.crear_bot(max_reintentos_transicion=2)
        bot._intento_actual = "intento-global"
        bot.ultimo_estado_navegacion = "PREPARAR_BUSCADOR"
        preparados = []
        enviados = []
        evidencias = []
        respuestas = iter([
            RuntimeError("BUSQUEDA_RECHAZADA_FORMULARIO"),
            {"fila": True},
        ])

        bot._preparar_busqueda = (
            lambda causa: preparados.append(causa) or "1233120140845"
        )
        bot._esperar_busqueda_habilitada = lambda causa, **kwargs: None
        bot._esperar_despues_captcha = lambda causa: None
        bot._enviar_busqueda_una_vez = (
            lambda causa, intento: enviados.append(intento)
        )
        bot._guardar_evidencia_busqueda = (
            lambda causa, intento, error: evidencias.append((intento, str(error))) or {}
        )

        def cambiar(causa, anterior, siguiente, accion, **extra):
            bot.ultimo_estado_navegacion = siguiente

        def esperar(causa):
            respuesta = next(respuestas)
            if isinstance(respuesta, Exception):
                bot.ultimo_estado_navegacion = "BUSQUEDA_RECHAZADA"
                raise respuesta
            return respuesta

        bot._cambiar_estado_navegacion = cambiar
        bot._esperar_resultados = esperar

        resultado = bot._buscar_resultado_con_reintentos(
            "12331-2014-0845", "1233120140845"
        )

        self.assertEqual(resultado, {"fila": True})
        self.assertEqual(preparados, ["12331-2014-0845"] * 2)
        self.assertEqual(len(enviados), 2)
        self.assertNotEqual(enviados[0], enviados[1])
        self.assertEqual(evidencias, [(1, "BUSQUEDA_RECHAZADA_FORMULARIO")])

    def test_maquina_rechaza_transicion_no_permitida(self):
        bot = self.crear_bot()
        bot.ultimo_estado_navegacion = "MOVIMIENTOS_LISTOS"

        with self.assertRaisesRegex(RuntimeError, "TRANSICION_NO_PERMITIDA"):
            bot._cambiar_estado_navegacion(
                "23331202202089",
                "MOVIMIENTOS_LISTOS",
                "BUSQUEDA_ENVIADA",
                "salto_invalido",
            )

    def test_consolidacion_conserva_origen_y_conteos(self):
        bot = self.crear_bot()
        bot._descriptores_actuales = [{"clave_carpeta": "carpeta-1"}]
        bot._aplicar_inferencia_consolidada = lambda datos, causa=None, **kwargs: datos
        actuacion = {
            "fecha": "24/02/2023",
            "detalle": "SENTENCIA",
            "CAUSA": "23331202202089",
            "CLAVE_CARPETA": "carpeta-1",
            "ORIGEN_CARPETA": "carpeta-1",
            "DEPENDENCIA_JURISDICCIONAL": "UNIDAD A",
            "CIUDAD_CARPETA": "QUININDÉ",
            "INSTANCIA_CARPETA": "1",
            "ORIGEN_DATA": "API",
        }

        resultado = bot._consolidar_resultados_carpetas(
            "23331202202089",
            [{
                "estado": "COMPLETA",
                "descriptor": {"fecha_ingreso": "24/02/2023 10:30"},
                "datos": {
                    "FECHA INICIO JUICIO": "01/03/2023",
                    "HISTORIAL_ACTUACIONES": [actuacion],
                },
            }],
        )

        consolidada = resultado["datos"]["HISTORIAL_ACTUACIONES"][0]
        self.assertEqual(consolidada["ORIGEN_CARPETA"], "carpeta-1")
        self.assertEqual(resultado["estado"], "COMPLETADO")
        self.assertEqual(resultado["carpetas_descubiertas"], 1)
        self.assertEqual(resultado["carpetas_completas"], 1)
        self.assertEqual(resultado["datos"]["FECHA INICIO JUICIO"], "24/02/2023")

    def test_actualizar_caso_actualiza_todas_las_filas_del_mismo_juicio(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["23331-2022-02089", "23331-2022-02089", "OTRA"],
            "ESTADO.1": ["ACTIVO", "FIN", "ACTIVO"],
            "ULTIMA ETAPA": [None, None, None],
        })

        actualizado = gestor.actualizar_caso(
            "23331-2022-02089", {"ULTIMA ETAPA": "6 LIQUIDACION Y EMBARGO"}
        )

        self.assertTrue(actualizado)
        self.assertEqual(
            gestor.df.loc[:1, "ULTIMA ETAPA"].tolist(),
            ["6 LIQUIDACION Y EMBARGO", "6 LIQUIDACION Y EMBARGO"],
        )
        self.assertIsNone(gestor.df.loc[2, "ULTIMA ETAPA"])

    def test_actualizar_caso_admite_fecha_en_columna_vacia_float64(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["23331-2025-00431", "OTRA"],
            "FECHA FIN ULTIMA FASE": [float("nan"), float("nan")],
        })
        self.assertEqual(
            str(gestor.df["FECHA FIN ULTIMA FASE"].dtype), "float64"
        )

        actualizado = gestor.actualizar_caso(
            "23331-2025-00431", {"FECHA FIN ULTIMA FASE": "31/01/2025"}
        )

        self.assertTrue(actualizado)
        self.assertEqual(gestor.df.loc[0, "FECHA FIN ULTIMA FASE"], "31/01/2025")
        self.assertTrue(pd.isna(gestor.df.loc[1, "FECHA FIN ULTIMA FASE"]))

    def test_depurar_duplicados_exactos_preserva_coincidencias_con_datos_distintos(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["23331-2025-00001", "23331-2025-00001", "23331-2025-00001"],
            "USUARIO": ["UNO", "UNO", "DOS"],
            "ESTADO.1": ["ACTIVO", "ACTIVO", "ABANDONO"],
        })

        eliminadas = gestor.depurar_filas_duplicadas_exactas()

        self.assertEqual(eliminadas, 1)
        self.assertEqual(len(gestor.df), 2)
        self.assertEqual(gestor.df["USUARIO"].tolist(), ["UNO", "DOS"])

    def test_obtener_casos_pendientes_filtra_por_usuario(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "SUCURSAL": ["SANTO DOMINGO", "SANTO DOMINGO", "SANTO DOMINGO"],
            "OFICINA": ["TSACHILAS", "TSACHILAS", "OTRA"],
            "USUARIO": ["LSTODOMINGO", "OTRO", "LSTODOMINGO"],
            "ESTADO": ["ACTIVO", "ACTIVO", "ACTIVO"],
            "NUMERO_JUICIO": ["CAUSA-001", "CAUSA-002", "CAUSA-003"],
        })
        gestor.filtros = {
            "sucursal": "", "oficina": "TSACHILAS",
            "usuario": "LSTODOMINGO", "estado_judicial": "ACTIVO",
            "columna_estado_judicial": "ESTADO",
        }

        self.assertEqual(gestor.obtener_casos_pendientes(), ["CAUSA-001"])

    def test_columnas_molde_respetan_orden_solicitado(self):
        columnas = GestorCasos.COLUMNAS_MOLDE_EXPORTACION

        self.assertLess(
            columnas.index("FECHA INICIO FASE ACTUAL"),
            columnas.index("ETAPA ACTUAL"),
        )
        self.assertEqual(columnas, [
            "FECHA INICIO JUICIO",
            "FECHA FIN ULTIMA FASE",
            "eta_id ULTIMA ETAPA",
            "ULTIMA ETAPA",
            "fas_id ULTIMA FASE",
            "ULTIMA FASE",
            "FECHA INICIO FASE ACTUAL",
            "eta_id ETAPA ACTUAL",
            "ETAPA ACTUAL",
            "fas_id FASE ACTUAL",
            "FASE ACTUAL",
            "DIAS TRANSCURRIDOS",
            "FECHA ULTIMA GESTION JUDICIAL",
            "ESTADO ULTIMA GESTION JUDICIAL",
        ])

    def test_normaliza_timestamp_iso_a_fecha_del_reporte(self):
        self.assertEqual(
            GestorCasos._normalizar_fecha_reporte(
                "2017-07-05T16:05:00.000+00:00"
            ),
            "05/07/2017",
        )
    def test_dias_transcurridos_usa_diferencia_de_dias_calendario(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "FECHA FIN ULTIMA FASE": ["08/10/2025"],
        })

        gestor.calcular_dias_transcurridos(datetime(2026, 8, 12))

        self.assertEqual(gestor.df.loc[0, "DIAS TRANSCURRIDOS"], 308)


    def test_exportacion_termina_en_fase_actual_y_dias_transcurridos(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["CAUSA-001"],
            "COMENTARIO_ULTIMO": [""],
            "HISTORIAL_ACTUACIONES": ["[]"],
            "UNNAMED: 39": [""],
            "FECHA FIN ULTIMA FASE": [
                "2017-07-05T16:05:00.000+00:00"
            ],
            "FECHA INICIO FASE ACTUAL": [None],
            "ETAPA ACTUAL": ["6 LIQUIDACION Y EMBARGO"],
            "FASE ACTUAL": ["6.3 EMBARGO"],
        })
        gestor.hoja = "migrado"

        with tempfile.TemporaryDirectory() as temporal:
            gestor.ruta_final = os.path.join(temporal, "reporte.xlsx")
            gestor.exportar_excel()
            exportado = pd.read_excel(
                gestor.ruta_final,
                sheet_name="Reporte",
                header=GestorCasos.FILA_ENCABEZADO_REPORTE - 1,
                dtype=str,
            )

        self.assertEqual(
            exportado.columns[-len(GestorCasos.COLUMNAS_MOLDE_EXPORTACION):].tolist(),
            GestorCasos.COLUMNAS_MOLDE_EXPORTACION,
        )
        self.assertEqual(exportado.loc[0, "eta_id ETAPA ACTUAL"], "15")
        self.assertEqual(exportado.loc[0, "fas_id FASE ACTUAL"], "90")
        self.assertEqual(exportado.loc[0, "FECHA FIN ULTIMA FASE"], "05/07/2017")

        self.assertEqual(
            exportado.loc[0, "FECHA INICIO FASE ACTUAL"], "05/07/2017"
        )

    def test_exportacion_acorta_etiquetas_de_citacion_y_congelamiento(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["CAUSA-001", "CAUSA-002"],
            "COMENTARIO_ULTIMO": ["", ""],
            "FECHA FIN ULTIMA FASE": ["01/01/2026", "02/01/2026"],
            "FECHA INICIO FASE ACTUAL": ["01/01/2026", "02/01/2026"],
            "ULTIMA FASE": [
                "2.1 CITACION (PERSONA/BOLETA)",
                "6.5 CONGELAMIENTO DE CUENTAS / CIERRE",
            ],
            "FASE ACTUAL": [
                "2.1 CITACION (PERSONA/BOLETA)",
                "6.5 CONGELAMIENTO DE CUENTAS / CIERRE",
            ],
        })
        gestor.hoja = "migrado"

        with tempfile.TemporaryDirectory() as temporal:
            gestor.ruta_final = os.path.join(temporal, "reporte.xlsx")
            gestor.exportar_excel()
            exportado = pd.read_excel(
                gestor.ruta_final,
                sheet_name="Reporte",
                header=GestorCasos.FILA_ENCABEZADO_REPORTE - 1,
                dtype=str,
            )

        esperadas = [
            "2.1 CITACION",
            "6.5 CONGELAMIENTO DE CUENTAS",
        ]
        self.assertEqual(exportado["ULTIMA FASE"].tolist(), esperadas)
        self.assertEqual(exportado["FASE ACTUAL"].tolist(), esperadas)
        self.assertEqual(
            gestor.df["ULTIMA FASE"].tolist(),
            [
                "2.1 CITACION (PERSONA/BOLETA)",
                "6.5 CONGELAMIENTO DE CUENTAS / CIERRE",
            ],
        )

    def test_reclasificacion_puede_limitarse_a_sucursal_y_estado_activo(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "SUCURSAL": ["QUITO", "QUITO", "LOS RIOS", " quito "],
            "ESTADO.1": ["ACTIVO", "FIN", "ACTIVO", " activo "],
            "NUMERO_JUICIO": [
                "17230-2020-00001",
                "17230-2020-00002",
                "12331-2020-00003",
                " 17230-2020-00004 ",
            ],
        })
        gestor.config = {
            "filtros_activos": {
                "columna_estado_judicial": "ESTADO.1",
                "estado_judicial": "ACTIVO",
            }
        }

        self.assertEqual(
            _causas_por_sucursal(gestor, "quito"),
            {"17230202000001", "17230202000004"},
        )

class PersistenciaTransaccionalTests(unittest.TestCase):
    def test_error_sin_datos_no_sobrescribe_evidencia_previa(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = os.path.join(temporal, "estado.db")
            cola = GestorCola(ruta_db=ruta)
            cola.poblar_cola(["CAUSA-001"])
            cola.obtener_siguiente()
            resultado_completo = {
                "estado": "COMPLETADO",
                "datos": {
                    "ULTIMA FASE": "1.3 CALIFICACION",
                    "HISTORIAL_ACTUACIONES": [
                        {"fecha": "01/01/2025", "detalle": "AUTO DE CALIFICACION"}
                    ],
                },
            }
            cola.registrar_resultado_transaccional(
                "CAUSA-001", resultado_completo, "TEST", estado_final="PROCESADO"
            )
            cola.registrar_resultado_transaccional(
                "CAUSA-001",
                {"estado": "ERROR_NAVEGACION", "datos": {}, "error": "CAPTCHA_TIMEOUT"},
                "TEST",
                estado_final="ERROR",
            )

            conexion = sqlite3.connect(ruta)
            try:
                estado = conexion.execute(
                    "SELECT estado FROM juicios WHERE numero_causa = ?", ("CAUSA-001",)
                ).fetchone()[0]
                datos_json = conexion.execute(
                    "SELECT datos_json FROM resultados_expediente WHERE numero_causa = ?",
                    ("CAUSA-001",),
                ).fetchone()[0]
            finally:
                conexion.close()

        self.assertEqual(estado, "ERROR")
        guardado = json.loads(datos_json)
        self.assertEqual(
            guardado["datos"]["HISTORIAL_ACTUACIONES"],
            resultado_completo["datos"]["HISTORIAL_ACTUACIONES"],
        )
        self.assertEqual(guardado["datos"]["fas_id ULTIMA FASE"], 79)

    def test_estado_final_parcial_se_confirma_en_misma_transaccion(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = os.path.join(temporal, "estado.db")
            cola = GestorCola(ruta_db=ruta)
            cola.poblar_cola(["CAUSA-001"])
            cola.obtener_siguiente()
            cola.registrar_resultado_transaccional(
                "CAUSA-001", {"estado": "PARCIAL"}, "TEST", estado_final="PARCIAL"
            )
            conexion = sqlite3.connect(ruta)
            try:
                estado = conexion.execute(
                    "SELECT estado FROM juicios WHERE numero_causa = ?", ("CAUSA-001",)
                ).fetchone()[0]
            finally:
                conexion.close()
        self.assertEqual(estado, "PARCIAL")

    def test_importar_logger_no_crea_filehandler(self):
        import src.logger_config as logger_config
        with patch("logging.FileHandler") as file_handler:
            importlib.reload(logger_config)
        file_handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
