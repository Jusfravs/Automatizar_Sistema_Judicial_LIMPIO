import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from src.gestor_casos import GestorCasos
from src.coordinador_concurrente import ExportadorResultadosEjecucion

from main import _ejecutar_lote_postgres, seleccionar_casos


class SeleccionLotesPostgresTests(unittest.TestCase):
    def test_hoja_seleccion_limita_causas_sin_alterar_csv(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "ESTADO": ["ACTIVO", "ACTIVO", "ACTIVO"],
            "NUMERO_JUICIO": ["01-01", "02-02", "03-03"],
        })
        gestor.ruta_excel = "origen.xlsx"
        gestor.filtros = {
            "estado_judicial": "ACTIVO",
            "hoja_seleccion_causas": "faltantes",
        }
        with patch("src.gestor_casos.pd.read_excel") as leer_hoja:
            leer_hoja.return_value = pd.DataFrame({
                "NUMERO_JUICIO": ["0101", "03-03"],
            })
            self.assertEqual(
                gestor.obtener_casos_pendientes(), ["01-01", "03-03"]
            )
            leer_hoja.assert_called_once_with(
                "origen.xlsx", sheet_name="faltantes", dtype=str,
            )
        self.assertEqual(len(gestor.df), 3)

    def test_exportacion_contiene_solo_causas_de_hoja_seleccion(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "CODIGO_JUICIO": [1, 2, 3],
            "NUMERO_JUICIO": ["01-01", "02-02", "03-03"],
        })
        gestor.ruta_excel = "origen.xlsx"
        gestor.filtros = {"hoja_seleccion_causas": "faltantes"}
        with patch("src.gestor_casos.pd.read_excel") as leer_hoja:
            leer_hoja.return_value = pd.DataFrame({
                "NUMERO_JUICIO": ["0101", "03-03"],
            })
            reporte, para_carga = gestor._preparar_exportacion()
        self.assertEqual(reporte["NUMERO_JUICIO"].tolist(), ["01-01", "03-03"])
        self.assertEqual(para_carga["NUMERO_JUICIO"].tolist(), ["01-01", "03-03"])
        self.assertEqual(len(gestor.df), 3)

    def test_pendientes_sin_limite_omite_completadas(self):
        gestor = SimpleNamespace(
            filtros={}, config={"base_de_datos": {"motor": "postgres"}},
            obtener_casos_pendientes=lambda: [str(i) for i in range(150)] + ["3"],
        )
        with patch("src.repositorio_postgres.RepositorioColaPostgres.desde_config") as pg, patch(
            "src.coordinador_concurrente.CoordinadorConcurrente"
        ) as coordinador:
            pg.return_value.listar_causas_procesadas.return_value = ["0", "1"]
            coordinador.return_value.ejecutar.return_value = {
                "ejecucion_id": "prueba", "estado": "COMPLETADA", "estadisticas": {},
            }
            _ejecutar_lote_postgres(gestor, ["--pendientes", "--omitir-procesados"], "perfil.json", "fallidos.txt", 2)
            self.assertEqual(coordinador.return_value.ejecutar.call_args.args[0], [str(i) for i in range(2, 150)])

    def test_revision_configurada_no_se_selecciona(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({"ESTADO": ["ACTIVO", "ACTIVO"], "NUMERO_JUICIO": ["01-01", "02-02"]})
        gestor.filtros = {"estado_judicial": "ACTIVO", "causas_revision_manual": {"0101": "Revisar"}}
        self.assertEqual(gestor.obtener_casos_pendientes(), ["02-02"])

    def test_ids_no_se_multiplican_al_recargar_csv(self):
        df = pd.DataFrame({"FAS_ID FASE ACTUAL": [1, 2], "FAS_ID FASE ACTUAL.1": [3, None], "fas_id FASE ACTUAL": [None, 4]})
        limpio = GestorCasos._unificar_columnas_id(df)
        self.assertEqual(list(limpio.columns), ["fas_id FASE ACTUAL"])
        self.assertEqual(limpio.iloc[:, 0].tolist(), [3, 4])
        pd.testing.assert_frame_equal(limpio, GestorCasos._unificar_columnas_id(limpio))

    def test_revision_conserva_fase_anterior_y_registra_comentario(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({"NUMERO_JUICIO": ["A"], "FASE ACTUAL": ["FASE PREVIA"]})
        fila = {"id": 1, "numero_causa": "A", "estado": "REVISION", "datos_json": {"datos": {"FASE ACTUAL": "REVISION MANUAL", "COMENTARIO_ULTIMO": "REVISION MANUAL: sin resultados"}}}
        repo = SimpleNamespace(listar_resultados=lambda *args, **kwargs: [fila])
        with patch.object(gestor, "guardar", return_value=True), patch.object(gestor, "exportar_excel"):
            ExportadorResultadosEjecucion(repo, gestor, "prueba", 1).sincronizar()
        self.assertEqual(gestor.df.loc[0, "FASE ACTUAL"], "FASE PREVIA")
        self.assertEqual(gestor.df.loc[0, "COMENTARIO_ULTIMO"], "REVISION MANUAL: sin resultados")

    def test_exclusion_fuera_del_lote_se_valida_en_todos_los_candidatos(self):
        self.assertEqual(
            seleccionar_casos(["A", "B", "C", "D"], ["--lote", "2", "--excluir", "D"]),
            ["A", "B"],
        )

    def test_continuacion_omite_procesadas_deduplica_y_mantiene_dos_workers(self):
        gestor = SimpleNamespace(
            filtros={},
            config={"base_de_datos": {"motor": "postgres"}},
            obtener_casos_pendientes=lambda: ["01-01", "02-02", "0202", "03-03", "04-04"],
        )
        with patch(
            "src.repositorio_postgres.RepositorioColaPostgres.desde_config"
        ) as crear_repo, patch(
            "src.coordinador_concurrente.CoordinadorConcurrente"
        ) as crear_coordinador:
            crear_repo.return_value.listar_causas_procesadas.return_value = ["0101"]
            crear_coordinador.return_value.ejecutar.return_value = {
                "ejecucion_id": "prueba", "estado": "COMPLETADA",
                "estadisticas": {"PROCESADO": 2},
            }
            _ejecutar_lote_postgres(
                gestor, ["--lote", "2", "--omitir-procesados"],
                "perfil.json", "fallidos.txt", 2,
            )
            crear_coordinador.assert_called_once_with(gestor, "perfil.json", trabajadores=2)
            crear_coordinador.return_value.ejecutar.assert_called_once_with(
                ["02-02", "03-03"], "fallidos.txt"
            )


if __name__ == "__main__":
    unittest.main()
