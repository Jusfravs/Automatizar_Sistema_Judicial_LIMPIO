import time
import unittest
from contextlib import closing, contextmanager
import sqlite3
import tempfile
from pathlib import Path

from src.coordinador_concurrente import (
    ExportadorResultadosEjecucion,
    RenovadorLease,
)
from src.ejecucion import ConfiguracionConcurrencia, extraer_trabajadores
from src.procesador_caso import (
    ProcesadorCaso,
    estado_terminal_para_resultado,
    resultado_es_recuperable,
)
from src.repositorio_postgres import RepositorioColaPostgres
from scripts.migrar_sqlite_a_postgres import FuenteSQLite, inspeccionar_fuentes


class ConfiguracionConcurrenciaTests(unittest.TestCase):
    def test_configuracion_segura_predeterminada(self):
        config = ConfiguracionConcurrencia.desde_config({})

        self.assertFalse(config.habilitada)
        self.assertEqual(config.trabajadores, 2)
        self.assertEqual(config.exportar_cada, 10)
        self.assertTrue(config.navegador_visible)

    def test_sqlite_rechaza_mas_de_un_trabajador(self):
        config = ConfiguracionConcurrencia.desde_config({})

        with self.assertRaisesRegex(RuntimeError, "POSTGRES_REQUERIDO"):
            config.validar_motor("sqlite", 2)
        self.assertEqual(config.validar_motor("sqlite", 1), 1)
        self.assertEqual(config.validar_motor("postgres", 2), 2)

    def test_extraer_workers_no_interfiere_con_modo_lote(self):
        cantidad, restantes = extraer_trabajadores(
            ["--config", "config.json", "--lote", "10", "--workers", "2"]
        )

        self.assertEqual(cantidad, 2)
        self.assertEqual(restantes, ["--config", "config.json", "--lote", "10"])

    def test_lease_debe_superar_dos_heartbeats(self):
        with self.assertRaisesRegex(ValueError, "LEASE_DEBE_SUPERAR"):
            ConfiguracionConcurrencia.desde_config(
                {"lease_segundos": 60, "heartbeat_segundos": 30}
            )


class ProcesadorCasoTests(unittest.TestCase):
    def test_formato_invalido_no_abre_navegador(self):
        procesador = ProcesadorCaso("https://ejemplo.local", {}, {})

        resultado = procesador.procesar("causa-invalida")

        self.assertEqual(resultado.estado, "ERROR_VERIFICACION_MANUAL")
        self.assertEqual(
            estado_terminal_para_resultado(resultado.estado),
            "REVISION",
        )
        self.assertIsNone(procesador._bot)

    def test_clasificacion_de_errores_recuperables(self):
        self.assertTrue(resultado_es_recuperable("ERROR_NAVEGACION"))
        self.assertTrue(resultado_es_recuperable("EXTRACCION_ERROR"))
        self.assertFalse(resultado_es_recuperable(
            "EXTRACCION_ERROR", "ARTEFACTOS_ERROR:[WinError 206] Ruta demasiado larga"
        ))
        self.assertFalse(resultado_es_recuperable("ERROR_VERIFICACION_MANUAL"))


class RepoResultadosFalso:
    def __init__(self):
        self.filas = []

    def listar_resultados(self, _ejecucion_id, despues_de=0):
        return [fila for fila in self.filas if fila["id"] > despues_de]


class GestorCasosFalso:
    def __init__(self):
        self.actualizados = []
        self.guardados = 0
        self.exportados = 0

    def actualizar_caso(self, causa, datos):
        self.actualizados.append((causa, datos))
        return True

    def guardar(self):
        self.guardados += 1
        return True

    def exportar_excel(self):
        self.exportados += 1


class ExportadorUnicoTests(unittest.TestCase):
    def test_exporta_cada_diez_y_conserva_pendientes_en_memoria(self):
        repo = RepoResultadosFalso()
        gestor = GestorCasosFalso()
        exportador = ExportadorResultadosEjecucion(repo, gestor, "run-1", 10)
        repo.filas = [
            {
                "id": indice,
                "numero_causa": "CAUSA-%02d" % indice,
                "estado": "PROCESADO",
                "datos_json": {"datos": {"ULTIMA FASE": "FASE"}},
            }
            for indice in range(1, 10)
        ]

        self.assertEqual(exportador.sincronizar(), 0)
        self.assertEqual(gestor.guardados, 0)
        repo.filas.append(
            {
                "id": 10,
                "numero_causa": "CAUSA-10",
                "estado": "PROCESADO",
                "datos_json": {"datos": {"ULTIMA FASE": "FASE"}},
            }
        )

        self.assertEqual(exportador.sincronizar(), 10)
        self.assertEqual(gestor.guardados, 1)
        self.assertEqual(gestor.exportados, 1)


class RepositorioPostgresContratoTests(unittest.TestCase):
    def test_reserva_usa_skip_locked_y_devuelve_trabajo(self):
        class Cursor:
            def __init__(self):
                self.consulta = ""

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, consulta, _parametros):
                self.consulta = consulta

            def fetchone(self):
                return {
                    "id": 7,
                    "numero_causa": "17230-2025-00001",
                    "intentos": 1,
                    "posicion": 3,
                }

        class Conexion:
            def __init__(self, cursor):
                self._cursor = cursor

            def cursor(self, **_kwargs):
                return self._cursor

        cursor = Cursor()
        repo = RepositorioColaPostgres("localhost", 5432, "u", "p", "d")

        @contextmanager
        def conexion():
            yield Conexion(cursor)

        repo._connection = conexion
        trabajo = repo.reservar_siguiente("run", "worker", 120)

        self.assertIn("FOR UPDATE SKIP LOCKED", cursor.consulta)
        self.assertEqual(trabajo.id, 7)
        self.assertEqual(trabajo.intentos, 1)


class HeartbeatTests(unittest.TestCase):
    def test_heartbeat_renueva_mientras_el_trabajo_sigue_activo(self):
        class Repo:
            def __init__(self):
                self.renovaciones = 0

            def renovar_lease(self, *_args):
                self.renovaciones += 1
                return True

        repo = Repo()
        with RenovadorLease(repo, 1, "worker", 2, 0.01):
            limite = time.monotonic() + 0.25
            while repo.renovaciones < 2 and time.monotonic() < limite:
                time.sleep(0.01)

        self.assertGreaterEqual(repo.renovaciones, 2)


class MigracionDryRunTests(unittest.TestCase):
    @staticmethod
    def _crear_sqlite(ruta, causas):
        with closing(sqlite3.connect(ruta)) as conn:
            conn.execute(
                """
                CREATE TABLE juicios (
                    numero_causa TEXT PRIMARY KEY,
                    estado TEXT,
                    ruta_html TEXT,
                    reintentos INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE resultados_expediente (
                    numero_causa TEXT PRIMARY KEY,
                    origen TEXT,
                    datos_json TEXT,
                    ruta_html TEXT,
                    actualizado_en TEXT
                )
                """
            )
            for causa in causas:
                conn.execute(
                    "INSERT INTO juicios VALUES (?, 'PROCESADO', NULL, 0)",
                    (causa,),
                )
                conn.execute(
                    """
                    INSERT INTO resultados_expediente
                    VALUES (?, 'TEST', '{"estado":"COMPLETADO"}', NULL,
                            '2026-09-22 10:00:00')
                    """,
                    (causa,),
                )
            conn.commit()

    def test_inspeccion_calcula_union_y_solapamientos_sin_escribir(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            ruta_a = raiz / "a.db"
            ruta_b = raiz / "b.db"
            self._crear_sqlite(ruta_a, ["A", "B"])
            self._crear_sqlite(ruta_b, ["B", "C"])
            fuentes = (
                FuenteSQLite("A", ruta_a, "A", 20),
                FuenteSQLite("B", ruta_b, "B", 10),
            )

            resumen = inspeccionar_fuentes(fuentes)

        self.assertEqual(resumen["filas_cola"], 4)
        self.assertEqual(resumen["resultados"], 4)
        self.assertEqual(resumen["causas_unicas"], 3)
        self.assertEqual(resumen["solapamientos"]["A__B"], 1)
        self.assertEqual(resumen["json_invalidos"], 0)


if __name__ == "__main__":
    unittest.main()
