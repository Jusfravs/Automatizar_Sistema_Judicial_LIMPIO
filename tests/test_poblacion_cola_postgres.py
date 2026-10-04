import os
import unittest
from contextlib import contextmanager

from src.repositorio_postgres import RepositorioColaPostgres


@unittest.skipUnless(os.getenv("TEST_POBLACION_POSTGRES") == "1", "Requiere PostgreSQL explicito")
class PoblacionPaginadaTests(unittest.TestCase):
    def test_1796_inserciones_y_conflictos_entre_paginas(self):
        repo = RepositorioColaPostgres.desde_config({})
        conn = repo._get_connection()
        try:
            # Tabla temporal: no modifica las colas ni las ejecuciones reales.
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TEMP TABLE cola_trabajo (
                        id BIGSERIAL PRIMARY KEY,
                        ejecucion_id TEXT NOT NULL,
                        numero_causa TEXT NOT NULL,
                        posicion INTEGER NOT NULL,
                        UNIQUE (ejecucion_id, numero_causa)
                    ) ON COMMIT DROP
                """)

            @contextmanager
            def conexion_temporal():
                yield conn

            repo._connection = conexion_temporal
            causas = ["causa-%04d" % i for i in range(1796)]
            self.assertEqual(repo.poblar_trabajos("prueba", causas), 1796)
            self.assertEqual(repo.poblar_trabajos("prueba", causas), 0)
            self.assertEqual(repo.poblar_trabajos("prueba", causas + ["nueva"]), 1)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*),count(DISTINCT numero_causa) FROM cola_trabajo")
                self.assertEqual(cur.fetchone(), (1797, 1797))
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
