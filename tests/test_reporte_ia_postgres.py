import unittest
from unittest.mock import patch

import pandas as pd

from src.reporte_ia import COLUMNAS_HITOS, COLUMNAS_REVISION, preparar_vistas_ia_postgres


CAUSA = "17230-2019-00001"


class CursorFalso:
    def __init__(self):
        self.consultas = []
        self.resultados = [
            [(1, CAUSA, "COMPLETADA", {"confianza": 0.9})],
            [(CAUSA, "act-1", "2026-10-22", "principal", 2, 3,
              "VIGENTE", "MOTOR", "v1")],
            [(1, CAUSA, "PENDIENTE", {"estado_actual": {"eta_id": 2, "fas_id": 3}},
              {"ETAPA ACTUAL": "2", "FASE ACTUAL": "3"}, None, None, None, None)],
        ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, consulta, parametros):
        self.consultas.append((consulta, parametros))

    def fetchall(self):
        return self.resultados[len(self.consultas) - 1]


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


class VistasPostgresTests(unittest.TestCase):
    def test_las_tres_consultas_se_restringen_a_las_causas_del_reporte(self):
        cursor = CursorFalso()
        conexion = ConexionFalsa(cursor)

        class RepoFalso:
            def _connection(self):
                return conexion

        with patch("src.repositorio_postgres.RepositorioColaPostgres.desde_config",
                   return_value=RepoFalso()):
            reporte, hitos, revisiones = preparar_vistas_ia_postgres(
                {"base_de_datos": {}},
                pd.DataFrame({"NUMERO_JUICIO": [CAUSA, CAUSA]}),
            )

        self.assertEqual(len(cursor.consultas), 3)
        for consulta, parametros in cursor.consultas:
            self.assertIn("numero_causa = ANY(%s)", consulta)
            self.assertEqual(parametros, ([CAUSA],))
        self.assertEqual(reporte["ESTADO AUDITORIA IA"].tolist(), ["COMPLETADA"] * 2)
        self.assertEqual(hitos["NUMERO_JUICIO"].tolist(), [CAUSA])
        self.assertEqual(revisiones["NUMERO_JUICIO"].tolist(), [CAUSA])

    def test_reporte_sin_causas_no_abre_conexion(self):
        with patch("src.repositorio_postgres.RepositorioColaPostgres.desde_config") as crear:
            reporte, hitos, revisiones = preparar_vistas_ia_postgres(
                {"base_de_datos": {}}, pd.DataFrame({"NUMERO_JUICIO": []}),
            )
        crear.assert_not_called()
        self.assertTrue(reporte.empty)
        self.assertEqual(hitos.columns.tolist(), COLUMNAS_HITOS)
        self.assertEqual(revisiones.columns.tolist(), COLUMNAS_REVISION)


if __name__ == "__main__":
    unittest.main()
