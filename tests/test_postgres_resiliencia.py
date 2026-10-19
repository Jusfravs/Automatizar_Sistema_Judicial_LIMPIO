"""Fallos de conexión PostgreSQL simulados, sin acceso a la red."""

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

from src.db_postgres import GestorPostgres


class GestorPostgresResilienciaTests(unittest.TestCase):
    def test_conexion_de_resultados_tiene_limites(self):
        with patch("src.db_postgres.psycopg2.connect") as conectar:
            GestorPostgres(host="localhost", user="u", password="falsa")._get_connection()
        opciones = conectar.call_args.kwargs
        self.assertEqual(opciones["connect_timeout"], 10)
        self.assertEqual(opciones["options"], "-c statement_timeout=120000")
        self.assertEqual(opciones["keepalives"], 1)

    def test_rollback_fallido_no_tapa_desconexion_original(self):
        gestor = GestorPostgres(host="localhost", user="u", password="falsa")
        conexion = MagicMock()
        conexion.closed = 0
        conexion.rollback.side_effect = psycopg2.InterfaceError("conexión cerrada")
        gestor._get_connection = lambda: conexion
        with patch("src.db_postgres.logger.warning"):
            with self.assertRaisesRegex(psycopg2.OperationalError, "fallo original"):
                with gestor._connection():
                    raise psycopg2.OperationalError("fallo original")
        conexion.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
