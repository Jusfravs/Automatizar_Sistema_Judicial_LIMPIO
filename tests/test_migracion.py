"""
Tests para verificar la migración y el esquema de la base de datos SQLite.
"""
import os
import sqlite3
import sys
import unittest
from unittest.mock import patch

# Permitir ejecutar el test desde la raíz del proyecto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.gestor_cola import GestorCola


class TestMigracionDB(unittest.TestCase):
    """Verifica que el esquema de la base de datos es correcto después de la migración."""

    DB_TEST = "test_estado_casos.db"

    def setUp(self):
        """Crea una instancia fresca de GestorCola con una DB temporal."""
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)
        self.cola = GestorCola(ruta_db=self.DB_TEST)

    def tearDown(self):
        """Elimina la DB temporal."""
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)

    def test_tablas_existen(self):
        """Las tres tablas requeridas deben existir tras la inicialización."""
        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = {row[0] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("juicios", tablas)
        self.assertIn("resultados_expediente", tablas)
        self.assertIn("eventos_extraccion", tablas)

    def test_verificar_esquema(self):
        """El método verificar_esquema() debe retornar True con el esquema completo."""
        self.assertTrue(self.cola.verificar_esquema())

    def test_columnas_tabla_juicios(self):
        """La tabla juicios debe tener las columnas correctas."""
        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(juicios)")
        columnas = {row[1] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("numero_causa", columnas)
        self.assertIn("estado", columnas)
        self.assertIn("ruta_html", columnas)
        self.assertIn("reintentos", columnas)

    def test_columnas_tabla_resultados(self):
        """La tabla resultados_expediente debe tener las columnas correctas."""
        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(resultados_expediente)")
        columnas = {row[1] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("numero_causa", columnas)
        self.assertIn("origen", columnas)
        self.assertIn("datos_json", columnas)
        self.assertIn("ruta_html", columnas)
        self.assertIn("actualizado_en", columnas)

    def test_columnas_tabla_eventos(self):
        """La tabla eventos_extraccion debe tener las columnas correctas."""
        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(eventos_extraccion)")
        columnas = {row[1] for row in cursor.fetchall()}
        conn.close()

        self.assertIn("id", columnas)
        self.assertIn("numero_causa", columnas)
        self.assertIn("origen", columnas)
        self.assertIn("detalle", columnas)
        self.assertIn("creado_en", columnas)


class TestPoblarCola(unittest.TestCase):
    """Verifica la funcionalidad de poblar y gestionar la cola."""

    DB_TEST = "test_cola_poblacion.db"

    def setUp(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)
        self.cola = GestorCola(ruta_db=self.DB_TEST)

    def tearDown(self):
        for ruta in (self.DB_TEST, "%s.rpa.lock" % self.DB_TEST):
            if os.path.exists(ruta):
                os.remove(ruta)

    def test_poblar_con_lista(self):
        """Poblar con una lista de causas debe insertar registros correctamente."""
        causas = ["07333-2018-00742", "07333-2016-02046", "09330-2020-00106"]
        self.cola.poblar_cola(causas)

        stats = self.cola.obtener_estadisticas()
        self.assertEqual(stats.get("PENDIENTE", 0), 3)

    def test_poblar_ignorar_duplicados(self):
        """Poblar dos veces con las mismas causas no debe duplicar registros."""
        causas = ["07333-2018-00742", "07333-2016-02046"]
        self.cola.poblar_cola(causas)
        self.cola.poblar_cola(causas)

        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM juicios")
        total = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(total, 2)

    def test_filtrar_causas_pendientes_excluye_estados_ya_atendidos(self):
        causas = [
            "CAUSA-PENDIENTE", "CAUSA-PROCESADA", "CAUSA-ERROR",
            "CAUSA-SIN-RESULTADOS", "CAUSA-NUEVA", "CAUSA-PENDIENTE",
        ]
        self.cola.poblar_cola(causas[:-1])
        self.cola.actualizar_estado("CAUSA-PROCESADA", "PROCESADO")
        self.cola.actualizar_estado("CAUSA-ERROR", "ERROR")
        self.cola.actualizar_estado("CAUSA-SIN-RESULTADOS", "SIN_RESULTADOS")

        resultado = self.cola.filtrar_causas_pendientes(causas)

        self.assertEqual(
            resultado, ["CAUSA-PENDIENTE", "CAUSA-NUEVA"]
        )

    def test_obtener_siguiente_atomico(self):
        """obtener_siguiente() debe cambiar el estado a EN_PROCESO."""
        self.cola.poblar_cola(["CAUSA-001", "CAUSA-002"])

        causa = self.cola.obtener_siguiente()
        self.assertEqual(causa, "CAUSA-001")

        stats = self.cola.obtener_estadisticas()
        self.assertEqual(stats.get("EN_PROCESO", 0), 1)
        self.assertEqual(stats.get("PENDIENTE", 0), 1)

    def test_reservar_causa_concreta_respeta_el_orden_del_lote(self):
        self.cola.poblar_cola(["CAUSA-001", "CAUSA-002"])

        estado_anterior = self.cola.reservar_causa("CAUSA-002")

        self.assertEqual(estado_anterior, "PENDIENTE")
        conn = sqlite3.connect(self.DB_TEST)
        try:
            estados = dict(conn.execute(
                "SELECT numero_causa, estado FROM juicios"
            ).fetchall())
        finally:
            conn.close()
        self.assertEqual(estados["CAUSA-001"], "PENDIENTE")
        self.assertEqual(estados["CAUSA-002"], "EN_PROCESO")

    def test_reserva_impide_tomar_una_causa_que_ya_esta_en_proceso(self):
        self.cola.poblar_cola(["CAUSA-001"])
        self.cola.reservar_causa("CAUSA-001")

        with self.assertRaisesRegex(RuntimeError, "CAUSA_YA_EN_PROCESO"):
            self.cola.reservar_causa("CAUSA-001", permitir_reproceso=True)

    def test_reproceso_explicito_puede_reservar_un_error(self):
        self.cola.poblar_cola(["CAUSA-001"])
        self.cola.actualizar_estado("CAUSA-001", "ERROR")

        with self.assertRaisesRegex(RuntimeError, "CAUSA_NO_PENDIENTE"):
            self.cola.reservar_causa("CAUSA-001")

        estado_anterior = self.cola.reservar_causa(
            "CAUSA-001", permitir_reproceso=True
        )
        self.assertEqual(estado_anterior, "ERROR")
        self.assertEqual(self.cola.obtener_estadisticas().get("EN_PROCESO"), 1)

    def test_bloqueo_impide_dos_ejecuciones_sobre_la_misma_base(self):
        segunda_cola = GestorCola(ruta_db=self.DB_TEST)

        with self.cola.bloquear_ejecucion():
            with self.assertRaisesRegex(RuntimeError, "OTRA_EJECUCION_ACTIVA"):
                with segunda_cola.bloquear_ejecucion():
                    self.fail("La segunda ejecución no debe adquirir el bloqueo")

        with segunda_cola.bloquear_ejecucion():
            pass

    def test_fallo_de_begin_conserva_la_excepcion_original(self):
        class ConexionBloqueada:
            in_transaction = False

            def __init__(self):
                self.cerrada = False
                self.rollback_invocado = False

            def execute(self, sentencia):
                if sentencia == "BEGIN IMMEDIATE":
                    raise sqlite3.OperationalError("database is locked")
                raise AssertionError("SQL inesperado: %s" % sentencia)

            def rollback(self):
                self.rollback_invocado = True

            def close(self):
                self.cerrada = True

        conexion = ConexionBloqueada()
        with patch("src.gestor_cola.sqlite3.connect", return_value=conexion):
            with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                with self.cola._exclusive_transaction():
                    pass

        self.assertFalse(conexion.rollback_invocado)
        self.assertTrue(conexion.cerrada)


class TestRecuperarHuerfanos(unittest.TestCase):
    """Verifica la recuperación de registros atrapados en EN_PROCESO."""

    DB_TEST = "test_huerfanos.db"

    def setUp(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)
        self.cola = GestorCola(ruta_db=self.DB_TEST)

    def tearDown(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)

    def test_recuperar_huerfanos(self):
        """Los registros EN_PROCESO deben volver a PENDIENTE."""
        self.cola.poblar_cola(["CAUSA-001", "CAUSA-002", "CAUSA-003"])

        # Simular que dos causas quedaron en EN_PROCESO
        self.cola.obtener_siguiente()  # CAUSA-001 → EN_PROCESO
        self.cola.obtener_siguiente()  # CAUSA-002 → EN_PROCESO

        recuperados = self.cola.recuperar_huerfanos()
        self.assertEqual(recuperados, 2)

        stats = self.cola.obtener_estadisticas()
        self.assertEqual(stats.get("EN_PROCESO", 0), 0)
        self.assertEqual(stats.get("PENDIENTE", 0), 3)

    def test_recuperar_sin_huerfanos(self):
        """Sin huérfanos, debe retornar 0."""
        self.cola.poblar_cola(["CAUSA-001"])
        self.assertEqual(self.cola.recuperar_huerfanos(), 0)

    def test_evento_de_recuperacion_registrado(self):
        """Debe registrar un evento en eventos_extraccion por cada huérfano."""
        self.cola.poblar_cola(["CAUSA-001"])
        self.cola.obtener_siguiente()

        self.cola.recuperar_huerfanos()

        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM eventos_extraccion WHERE origen = 'RECUPERACION'"
        )
        total_eventos = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(total_eventos, 1)


class TestRegistrarResultado(unittest.TestCase):
    """Verifica el registro transaccional de resultados."""

    DB_TEST = "test_resultados.db"

    def setUp(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)
        self.cola = GestorCola(ruta_db=self.DB_TEST)

    def tearDown(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)

    def test_registrar_resultado(self):
        """Registrar un resultado debe cambiar el estado a PROCESADO."""
        self.cola.poblar_cola(["CAUSA-001"])
        self.cola.obtener_siguiente()  # EN_PROCESO

        datos = {
            "FECHA INICIO JUICIO": "15/03/2020",
            "ETAPA_PROCESAL": "EJECUCIÓN",
            "FASE_PROCESAL": "SENTENCIA",
        }
        self.cola.registrar_resultado_transaccional(
            "CAUSA-001", datos, origen="TEST", ruta_html=None
        )

        stats = self.cola.obtener_estadisticas()
        self.assertEqual(stats.get("PROCESADO", 0), 1)

    def test_resultado_en_tabla_resultados(self):
        """El resultado debe persistirse en la tabla resultados_expediente."""
        self.cola.poblar_cola(["CAUSA-001"])
        self.cola.obtener_siguiente()

        datos = {"ETAPA_PROCESAL": "INSTRUCCIÓN"}
        self.cola.registrar_resultado_transaccional(
            "CAUSA-001", datos, origen="DOM_BS4"
        )

        conn = sqlite3.connect(self.DB_TEST)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT datos_json, origen FROM resultados_expediente WHERE numero_causa = 'CAUSA-001'"
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertIn("INSTRUCCIÓN", row[0])
        self.assertEqual(row[1], "DOM_BS4")


class TestReiniciarErrores(unittest.TestCase):
    """Verifica la lógica de reintentos de registros con estado ERROR."""

    DB_TEST = "test_reintentos.db"

    def setUp(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)
        self.cola = GestorCola(ruta_db=self.DB_TEST)

    def tearDown(self):
        if os.path.exists(self.DB_TEST):
            os.remove(self.DB_TEST)

    def test_reiniciar_errores(self):
        """Los registros en ERROR con reintentos < max deben volver a PENDIENTE."""
        self.cola.poblar_cola(["CAUSA-001", "CAUSA-002"])
        self.cola.actualizar_estado("CAUSA-001", "ERROR")
        self.cola.actualizar_estado("CAUSA-002", "ERROR")

        reiniciados = self.cola.reiniciar_errores(max_reintentos=3)
        self.assertEqual(reiniciados, 2)

        stats = self.cola.obtener_estadisticas()
        self.assertEqual(stats.get("PENDIENTE", 0), 2)
        self.assertEqual(stats.get("ERROR", 0), 0)

    def test_no_reiniciar_si_max_alcanzado(self):
        """Los registros que ya alcanzaron el máximo de reintentos no deben reiniciarse."""
        self.cola.poblar_cola(["CAUSA-001"])
        # Simular 3 reintentos previos
        conn = sqlite3.connect(self.DB_TEST)
        conn.execute("UPDATE juicios SET estado = 'ERROR', reintentos = 3 WHERE numero_causa = 'CAUSA-001'")
        conn.commit()
        conn.close()

        reiniciados = self.cola.reiniciar_errores(max_reintentos=3)
        self.assertEqual(reiniciados, 0)


if __name__ == "__main__":
    unittest.main()
