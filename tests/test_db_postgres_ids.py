import unittest
from contextlib import contextmanager

from src.db_postgres import GestorPostgres


class CursorFalso:
    def __init__(self):
        self.operaciones = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, consulta, parametros=None):
        self.operaciones.append((consulta, parametros))


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class PersistenciaPostgresIdsTests(unittest.TestCase):
    def test_upsert_persiste_ids_y_payload_enriquecido(self):
        cursor = CursorFalso()
        gestor = GestorPostgres.__new__(GestorPostgres)

        @contextmanager
        def conexion():
            yield ConexionFalsa(cursor)

        gestor._connection = conexion
        gestor.registrar_resultado(
            "CAUSA-1",
            {
                "estado": "COMPLETADO",
                "datos": {
                    "ULTIMA ETAPA": "1 PRESENTACION Y CALIFICACION",
                    "ULTIMA FASE": "1.3 CALIFICACION",
                    "ETAPA ACTUAL": "2 CITACION",
                    "FASE ACTUAL": "2.1 CITACION (PERSONA/BOLETA)",
                },
            },
        )

        consulta, parametros = cursor.operaciones[0]
        self.assertIn("eta_id_ultima_etapa", consulta)
        self.assertIn("fas_id_fase_actual", consulta)
        self.assertEqual(parametros[3:7], (10, "1 PRESENTACION Y CALIFICACION", 79, "1.3 CALIFICACION"))
        self.assertEqual(parametros[8:12], (11, "2 CITACION", 80, "2.1 CITACION"))
        payload = parametros[-1].adapted
        self.assertEqual(payload["datos"]["fas_id FASE ACTUAL"], 80)


if __name__ == "__main__":
    unittest.main()
