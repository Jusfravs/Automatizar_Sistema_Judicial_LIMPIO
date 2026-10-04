"""Recorridos de la interfaz sin tocar PostgreSQL ni el portal judicial."""

import tempfile
import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from consola import preparar
from src.configuracion_lotes import cargar_comun, guardar_json_atomico
from src.interfaz_cmd import InterfazCMD
from src.normalizacion_excel import leer_y_validar


class InterfazCMDTests(unittest.TestCase):
    def test_conexion_guarda_solo_datos_no_secretos(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "config_consola.json"
            guardar_json_atomico(ruta, {"base_de_datos": {"motor": "postgres", "host": "localhost"}})

            class API:
                CONFIG_COMUN = ruta
                cargar_comun = staticmethod(cargar_comun)
                guardar_json_atomico = staticmethod(guardar_json_atomico)

            interfaz = InterfazCMD(API)
            with patch.object(interfaz, "_seleccionar", return_value=1), \
                 patch.object(interfaz, "_pausa"), \
                 patch("builtins.input", side_effect=["db.example.org", "5432", "judicial", "usuario", "ca.pem"]), \
                 patch("getpass.getpass", return_value="clave-privada"), \
                 patch.dict(os.environ, {}, clear=False):
                interfaz._configurar_conexion()
                self.assertEqual(os.environ["POSTGRES_PASSWORD"], "clave-privada")
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(guardado["base_de_datos"]["host"], "db.example.org")
            self.assertEqual(guardado["base_de_datos"]["sslmode"], "verify-full")
            self.assertNotIn("clave-privada", ruta.read_text(encoding="utf-8"))

    def test_menu_elige_por_numero_y_vuelve(self):
        class API:
            RAIZ = Path.cwd()

        interfaz = InterfazCMD(API)
        interfaz.interactiva = False
        with patch("builtins.input", side_effect=["2", "0"]):
            self.assertEqual(interfaz._seleccionar("Prueba", ["Uno", "Dos"]), 1)
            self.assertIsNone(interfaz._seleccionar("Prueba", ["Uno", "Dos"]))
        self.assertIn("50%", interfaz._progreso(5, 10))

    def test_preparar_desde_menu_elige_carpeta_automaticamente(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            excel = raiz / "casos.xlsx"
            pd.DataFrame({
                "CODIGO_JUICIO": ["001"],
                "NUMERO_JUICIO": ["07331-2024-00277"],
                "SUCURSAL": ["QUITO"],
                "ESTADO": ["ACTIVO"],
            }).to_excel(excel, index=False)
            (raiz / "config_consola.json").write_text(
                '{"base_de_datos":{"motor":"postgres"},"filtros_activos":{"estado_judicial":"ACTIVO"}}',
                encoding="utf-8")

            class API:
                RAIZ = raiz
                CONFIG_COMUN = raiz / "config_consola.json"
                leer_y_validar = staticmethod(leer_y_validar)
                preparar = staticmethod(preparar)

            interfaz = InterfazCMD(API)
            with patch.object(interfaz, "_elegir_excel", return_value=excel), \
                 patch.object(interfaz, "_seleccionar", return_value=0), \
                 patch.object(interfaz, "_pausa"):
                interfaz._preparar()
            self.assertIsNotNone(interfaz.perfil)
            self.assertTrue((interfaz.perfil / "manifiesto.json").is_file())
            self.assertFalse((interfaz.perfil / "config.json").exists())
            self.assertTrue(os.path.samefile(interfaz.perfil.parent, raiz / "outputs" / "lotes"))


if __name__ == "__main__":
    unittest.main()
