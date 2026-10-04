"""Contratos de entrada de Excel y aislamiento del perfil de consola."""

import json
import hashlib
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, Mock

import pandas as pd

from consola import aplicar_migraciones, preparar
from src.configuracion_lotes import actualizar_casos, configuracion_efectiva, migrar_lote_anterior
from src.gestor_casos import GestorCasos
from src.normalizacion_excel import leer_y_validar
from src.repositorio_postgres import RepositorioColaPostgres


class ConsolaExcelTests(unittest.TestCase):
    def _excel(self, ruta, duplicado=False):
        df = pd.DataFrame({
            "Código de juicio": ["001", "001" if duplicado else "002"],
            "Número de juicio": ["07331/2024/00277", "07331-2024-00278"],
            "Sucursal": ["QUITO", "QUITO"],
            "Estado": ["COMERCIAL", "COMERCIAL"],
            "Estado.1": ["ACTIVO", "INACTIVO"],
        })
        with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Reporte", startrow=5, index=False)

    def test_normaliza_cabecera_y_estado_judicial(self):
        with tempfile.TemporaryDirectory() as temporal:
            excel = Path(temporal) / "entrada.xlsx"
            self._excel(excel)
            df, resumen = leer_y_validar(excel)
            self.assertEqual(resumen["fila_encabezado"], 6)
            self.assertEqual(resumen["activas"], 1)
            self.assertEqual(df["NUMERO_JUICIO"].tolist()[0], "07331-2024-00277")
            self.assertEqual(df["ESTADO"].tolist(), ["ACTIVO", "INACTIVO"])

    def test_preparar_aisla_archivos_y_el_motor_lee_el_csv(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            excel = carpeta / "entrada.xlsx"
            self._excel(excel)
            base = carpeta / "base.json"
            base.write_text(json.dumps({
                "base_de_datos": {"motor": "postgres", "password_env": "POSTGRES_PASSWORD"},
                "filtros_activos": {"sucursal": "TODAS", "estado_judicial": "ACTIVO",
                                   "columna_estado_judicial": "ESTADO"},
                "navegacion": {"url_portal": "https://ejemplo.invalid"},
            }), encoding="utf-8")
            salida = carpeta / "lote"
            resultado = preparar(excel, salida, base)
            self.assertEqual(resultado["filas"], 2)
            config = configuracion_efectiva(salida, base)
            self.assertEqual(config["base_de_datos"]["motor"], "postgres")
            self.assertNotIn("host", config["base_de_datos"])
            self.assertFalse((salida / "config.json").exists())
            self.assertEqual(GestorCasos(str(base), config_efectiva=config).obtener_casos_pendientes(),
                             ["07331-2024-00277"])
            self.assertTrue((salida / "origen.xlsx").is_file())
            self.assertEqual((salida / "reporte_trabajo.csv").read_bytes(),
                             (salida / "reporte_trabajo.csv.bak").read_bytes())
            self.assertEqual((salida / "casos.txt").read_text(encoding="utf-8"),
                             "07331-2024-00277\n")
            self.assertEqual((salida / "casos_fallidos.txt").read_text(encoding="utf-8"), "")
            (salida / "casos_fallidos.txt").write_text("NO_BORRAR", encoding="utf-8")
            repetido = preparar(excel, carpeta / "otro_lote", base)
            self.assertTrue(repetido["reutilizado"])
            self.assertTrue(os.path.samefile(repetido["directorio"], salida))
            self.assertEqual((salida / "casos_fallidos.txt").read_text(encoding="utf-8"), "NO_BORRAR")
            config_anterior = config["_config_sha256"]
            comun = json.loads(base.read_text(encoding="utf-8"))
            comun["filtros_activos"]["estado_judicial"] = "INACTIVO"
            base.write_text(json.dumps(comun), encoding="utf-8")
            self.assertEqual(actualizar_casos(salida, base), ["07331-2024-00278"])
            self.assertNotEqual(configuracion_efectiva(salida, base)["_config_sha256"], config_anterior)

    def test_migra_lote_anterior_sin_borrar_archivos(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            excel = raiz / "entrada.xlsx"
            self._excel(excel)
            base = raiz / "comun.json"
            base.write_text(json.dumps({"base_de_datos": {"motor": "postgres"},
                                        "filtros_activos": {"estado_judicial": "ACTIVO"}}), encoding="utf-8")
            lote = raiz / "lote"
            lote.mkdir()
            excel.rename(lote / "origen.xlsx")
            pd.DataFrame({"CODIGO_JUICIO": ["001"], "NUMERO_JUICIO": ["07331-2024-00277"],
                          "SUCURSAL": ["QUITO"], "ESTADO": ["ACTIVO"]}).to_csv(lote / "reporte_trabajo.csv", index=False)
            (lote / "config.json").write_text('{"perfil":"perfil-antiguo"}', encoding="utf-8")
            sha = hashlib.sha256((lote / "origen.xlsx").read_bytes()).hexdigest()
            (lote / "manifiesto.json").write_text(json.dumps({"sha256": sha, "hoja": "Reporte",
                                                          "filas": 1}), encoding="utf-8")
            migrar_lote_anterior(lote, base)
            self.assertEqual(configuracion_efectiva(lote, base)["perfil"], "perfil-antiguo")
            self.assertTrue((lote / "config.json").is_file())
            self.assertTrue((lote / "reporte_trabajo.csv.bak").is_file())
            self.assertTrue((lote / "casos_fallidos.txt").is_file())
            self.assertEqual((lote / "casos.txt").read_text(encoding="utf-8"), "07331-2024-00277\n")

    def test_rechaza_identidad_duplicada_sin_crear_perfil(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            excel = carpeta / "entrada.xlsx"
            self._excel(excel, duplicado=True)
            with self.assertRaisesRegex(ValueError, "CODIGO_JUICIO_DUPLICADO"):
                leer_y_validar(excel)

    def test_excel_modificado_crea_otro_lote(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            excel = raiz / "entrada.xlsx"
            base = raiz / "comun.json"
            base.write_text(json.dumps({"base_de_datos": {"motor": "postgres"},
                                        "filtros_activos": {"estado_judicial": "ACTIVO"}}), encoding="utf-8")
            self._excel(excel)
            uno = preparar(excel, raiz / "lotes" / "primero", base)
            pd.DataFrame({"CODIGO_JUICIO": ["003"], "NUMERO_JUICIO": ["07331-2024-00279"],
                          "SUCURSAL": ["QUITO"], "ESTADO": ["ACTIVO"]}).to_excel(excel, index=False)
            dos = preparar(excel, raiz / "lotes" / "segundo", base)
            self.assertNotEqual(uno["directorio"], dos["directorio"])
            self.assertFalse(dos["reutilizado"])

    def test_main_recibe_configuracion_efectiva_sin_archivo_de_lote(self):
        import main

        config = {"base_de_datos": {"motor": "postgres"}, "concurrencia": {}, "rutas": {}}
        repo = Mock(config=config)
        with patch.object(main, "GestorCasos", return_value=repo) as crear, \
             patch.object(main, "_ejecutar_lote_postgres", return_value=None):
            main.main(["--config", "comun.json", "--pendientes", "--workers", "1"],
                      config_efectiva=config)
        crear.assert_called_once_with("comun.json", config_efectiva=config)

    def test_repositorio_registra_huella_en_ejecucion(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def execute(self, consulta, parametros):
                self.consulta, self.parametros = consulta, parametros

        class Conexion:
            def cursor(self):
                return cursor

        cursor = Cursor()

        @contextmanager
        def conexion():
            yield Conexion()

        repo = RepositorioColaPostgres.__new__(RepositorioColaPostgres)
        repo._connection = conexion
        huella = "a" * 64
        repo.crear_ejecucion("perfil", 2, 1, config_sha256=huella)
        self.assertIn("config_sha256", cursor.consulta)
        self.assertEqual(cursor.parametros[-1], huella)

    def test_migracion_guiada_aplica_solo_la_003(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def execute(self, consulta, parametros=None):
                consultas.append(consulta)

            def fetchone(self):
                return None

        class Conexion:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def cursor(self):
                return Cursor()

            def close(self):
                pass

        consultas = []
        repo = Mock(host="localhost", port=5432, dbname="prueba", sslmode="prefer", sslrootcert="")
        with patch("consola._repositorio", return_value=repo), \
             patch("psycopg2.connect", return_value=Conexion()):
            aplicar_migraciones({"base_de_datos": {"motor": "postgres"}}, "admin", "secreto")
        self.assertEqual(sum("ALTER TABLE" in consulta for consulta in consultas), 1)
        self.assertTrue(any("INSERT INTO public.schema_migrations" in consulta for consulta in consultas))


if __name__ == "__main__":
    unittest.main()
