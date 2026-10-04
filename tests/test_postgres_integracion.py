import os
import unittest


DB_INTEGRACION = os.getenv("POSTGRES_DB", "")
EJECUTAR_INTEGRACION_POSTGRES = (
    os.getenv("RUN_POSTGRES_INTEGRATION") == "1"
    and DB_INTEGRACION == "casos_judiciales_test"
)


@unittest.skipUnless(
    EJECUTAR_INTEGRACION_POSTGRES,
    "Defina RUN_POSTGRES_INTEGRATION=1 y POSTGRES_DB=casos_judiciales_test.",
)
class TestPostgresIntegracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.db_postgres import GestorPostgres

        cls.gestor = GestorPostgres()

    def test_conexion_exitosa(self):
        with self.gestor._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                res = cur.fetchone()
                self.assertEqual(res[0], 1)

    def test_esquema_completo_para_procesamiento(self):
        from src.repositorio_postgres import RepositorioColaPostgres

        repositorio = RepositorioColaPostgres.desde_config(
            {"nombre_db": "casos_judiciales_test"}
        )
        self.assertTrue(repositorio.verificar_esquema())

    def test_consultar_vistas(self):
        fases = self.gestor.obtener_resumen_fases()
        self.assertIsInstance(fases, list)
        
        revision = self.gestor.obtener_casos_revision_manual()
        self.assertIsInstance(revision, list)

    def test_registro_y_recuperacion_expediente(self):
        causa_test = "99999-9999-99999"
        resultado_mock = {
            "estado": "PROCESADO",
            "datos": {
                "ULTIMA ETAPA": "1 PRESENTACION Y CALIFICACION",
                "ULTIMA FASE": "1.3 CALIFICACION",
                "FECHA FIN ULTIMA FASE": "2026-08-19",
                "ETAPA ACTUAL": "2 CITACION",
                "FASE ACTUAL": "2.1 CITACION (PERSONA/BOLETA)",
                "ACTOR": "BANCO PRUEBA S.A.",
                "DEMANDADO": "JUAN PEREZ",
                "HISTORIAL_ACTUACIONES": [
                    {"fecha": "2026-08-19", "actuacion": "AUTO DE CALIFICACION", "detalle": "CALIFICA DEMANDA"}
                ]
            }
        }
        self.gestor.registrar_resultado(causa_test, resultado_mock, ciudad="TEST")
        
        with self.gestor._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ultima_fase, actor FROM expedientes WHERE numero_causa = %s", (causa_test,))
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "1.3 CALIFICACION")
                self.assertEqual(row[1], "BANCO PRUEBA S.A.")
                
                # Cleanup
                cur.execute("DELETE FROM expedientes WHERE numero_causa = %s", (causa_test,))

if __name__ == "__main__":
    unittest.main()
