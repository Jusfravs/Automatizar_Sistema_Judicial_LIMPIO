"""Pruebas de tolerancia a bloqueos temporales del CSV en Windows/OneDrive."""

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.gestor_casos import GestorCasos


def _gestor_con_csv(ruta):
    gestor = GestorCasos.__new__(GestorCasos)
    gestor.ruta_csv = str(ruta)
    gestor.df = pd.DataFrame({"NUMERO_JUICIO": ["CAUSA-001"]})
    gestor.df.to_csv(ruta, index=False)
    return gestor


class RespaldoCsvTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temporal.name)

    def tearDown(self):
        self.temporal.cleanup()

    def test_guardar_reintenta_bloqueo_temporal_al_crear_respaldo(self):
        gestor = _gestor_con_csv(self.tmp_path / "reporte.csv")
        bloqueo = OSError(errno.EBUSY, "archivo en uso")

        with patch(
            "src.gestor_casos.shutil.copy2", side_effect=[bloqueo, None]
        ) as copiar, patch("src.gestor_casos.time.sleep") as dormir:
            self.assertTrue(gestor.guardar())

        self.assertEqual(copiar.call_count, 2)
        dormir.assert_called_once_with(0.5)

    def test_guardar_no_reintenta_error_no_transitorio_en_respaldo(self):
        gestor = _gestor_con_csv(self.tmp_path / "reporte.csv")

        with patch(
            "src.gestor_casos.shutil.copy2",
            side_effect=OSError(errno.ENOENT, "no existe"),
        ) as copiar, patch("src.gestor_casos.time.sleep") as dormir:
            self.assertFalse(gestor.guardar())

        self.assertEqual(copiar.call_count, 1)
        dormir.assert_not_called()

    def test_guardar_reemplaza_el_csv_de_forma_atomica(self):
        ruta = self.tmp_path / "reporte.csv"
        gestor = _gestor_con_csv(ruta)
        gestor.df.loc[0, "ESTADO"] = "ACTUALIZADO"
        reemplazos = []
        reemplazar_real = os.replace

        def reemplazar(origen, destino):
            origen = Path(origen)
            reemplazos.append((origen, Path(destino)))
            self.assertTrue(origen.exists())
            self.assertNotEqual(origen, ruta)
            reemplazar_real(origen, destino)

        with patch("src.gestor_casos.os.replace", side_effect=reemplazar):
            self.assertTrue(gestor.guardar())

        self.assertEqual(len(reemplazos), 1)
        self.assertEqual(reemplazos[0][1], ruta)
        guardado = pd.read_csv(ruta)
        self.assertEqual(guardado.loc[0, "ESTADO"], "ACTUALIZADO")

    def test_guardar_elimina_el_temporal_si_falla_la_escritura(self):
        ruta = self.tmp_path / "reporte.csv"
        gestor = _gestor_con_csv(ruta)

        with patch.object(
            gestor.df, "to_csv", side_effect=OSError("fallo simulado")
        ):
            self.assertFalse(gestor.guardar())

        self.assertEqual(list(self.tmp_path.glob(".reporte.csv.*.tmp")), [])

    def test_cargar_excel_usa_una_sombra_unica_y_la_elimina(self):
        ruta = self.tmp_path / "origen.xlsx"
        ruta.write_bytes(b"contenido simulado")
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.ruta_excel = str(ruta)
        gestor.hoja = "migrado"
        rutas_leidas = []

        def leer(ruta_lectura, **_kwargs):
            ruta_lectura = Path(ruta_lectura)
            rutas_leidas.append(ruta_lectura)
            self.assertTrue(ruta_lectura.exists())
            return pd.DataFrame({"SUCURSAL": ["PRUEBA"]})

        with patch("src.gestor_casos.pd.read_excel", side_effect=leer):
            resultado = gestor._cargar_excel_robusto()

        self.assertEqual(list(resultado["SUCURSAL"]), ["PRUEBA"])
        self.assertEqual(len(rutas_leidas), 1)
        self.assertNotEqual(rutas_leidas[0], ruta)
        self.assertFalse(rutas_leidas[0].exists())

    def test_cargar_excel_recurre_al_original_si_no_puede_crear_sombra(self):
        ruta = self.tmp_path / "origen.xlsx"
        ruta.write_bytes(b"contenido simulado")
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.ruta_excel = str(ruta)
        gestor.hoja = "migrado"

        with patch(
            "src.gestor_casos.shutil.copy2",
            side_effect=PermissionError("archivo bloqueado"),
        ), patch(
            "src.gestor_casos.pd.read_excel",
            return_value=pd.DataFrame({"SUCURSAL": ["PRUEBA"]}),
        ) as leer:
            resultado = gestor._cargar_excel_robusto()

        self.assertEqual(list(resultado["SUCURSAL"]), ["PRUEBA"])
        self.assertEqual(Path(leer.call_args.args[0]), ruta)
        self.assertEqual(list(self.tmp_path.glob("_excel_shadow_*.xlsx")), [])
