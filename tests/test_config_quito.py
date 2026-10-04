import json
import sqlite3
import unittest
from pathlib import Path

import pandas as pd


RAIZ = Path(__file__).resolve().parents[1]


class TestConfiguracionQuito(unittest.TestCase):
    def setUp(self):
        self.ruta_config = RAIZ / "config_quito.json"
        self.config = json.loads(self.ruta_config.read_text(encoding="utf-8"))

    def test_configuracion_cubre_quito_completo_sin_usuario_restrictivo(self):
        filtros = self.config["filtros_activos"]
        self.assertEqual(filtros["sucursal"], "QUITO")
        self.assertEqual(filtros["oficina"], "QUITO SUR")
        self.assertEqual(filtros["usuario"], "")
        self.assertEqual(filtros["estado_judicial"], "ACTIVO")
        self.assertEqual(filtros["columna_estado_judicial"], "ESTADO")

    def test_rutas_quito_estan_aisladas(self):
        rutas = self.config["rutas"]
        for clave in (
            "archivo_csv",
            "archivo_origen",
            "archivo_excel_final",
            "archivo_db",
            "archivo_casos_fallidos",
        ):
            self.assertTrue(rutas[clave].replace("\\", "/").startswith("data/quito/"))

    def test_datos_regionales_tienen_alcance_completo(self):
        rutas = self.config["rutas"]
        ruta_origen = RAIZ / rutas["archivo_origen"]
        ruta_csv = RAIZ / rutas["archivo_csv"]
        if not ruta_csv.exists():
            self.skipTest("El entorno Quito todavia no fue preparado")
        df_origen = pd.read_excel(
            ruta_origen,
            sheet_name=rutas.get("hoja_lectura", "QUITO"),
        )
        df = pd.read_csv(ruta_csv, low_memory=False)
        self.assertEqual(len(df_origen), 129)
        self.assertEqual(len(df_origen.columns), 31)
        self.assertEqual(len(df), 129)
        self.assertEqual(df["NUMERO_JUICIO"].astype(str).nunique(), 128)
        self.assertEqual(set(df["SUCURSAL"].astype(str).str.upper()), {"QUITO"})
        self.assertEqual(set(df["OFICINA"].astype(str).str.upper()), {"QUITO SUR"})
        self.assertEqual(set(df["ESTADO"].astype(str).str.upper()), {"ACTIVO"})
        self.assertTrue(set(df_origen.columns).issubset(df.columns))

        ruta_db = RAIZ / rutas["archivo_db"]
        with sqlite3.connect(ruta_db) as conexion:
            estados = dict(conexion.execute(
                "SELECT estado, COUNT(*) FROM juicios GROUP BY estado"
            ).fetchall())
            resultados = conexion.execute(
                "SELECT COUNT(*) FROM resultados_expediente"
            ).fetchone()[0]
            eventos = conexion.execute(
                "SELECT COUNT(*) FROM eventos_extraccion"
            ).fetchone()[0]
        self.assertEqual(sum(estados.values()), 128)
        self.assertTrue(
            set(estados).issubset(
                {
                    "PENDIENTE", "EN_PROCESO", "PROCESADO", "PARCIAL",
                    "SIN_RESULTADOS", "ERROR", "EXCLUIDO_NO_CORRESPONDE",
                }
            )
        )
        self.assertGreaterEqual(resultados, 0)
        self.assertGreaterEqual(eventos, 0)
        self.assertTrue((RAIZ / rutas["archivo_casos_fallidos"]).exists())

        try:
            df_final = pd.read_excel(RAIZ / rutas["archivo_excel_final"])
            self.assertEqual(len(df_final), 129)
            for columna in (
                "ULTIMA ETAPA",
                "ULTIMA FASE",
                "FECHA FIN ULTIMA FASE",
                "ETAPA ACTUAL",
                "FASE ACTUAL",
            ):
                self.assertIn(columna, df_final.columns)
        except PermissionError:
            self.skipTest(f"El archivo Excel final {rutas['archivo_excel_final']} está abierto en otra aplicación.")


if __name__ == "__main__":
    unittest.main()
