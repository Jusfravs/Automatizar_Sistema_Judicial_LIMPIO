import json
import unittest

import pandas as pd

from src.gestor_casos import GestorCasos
from src.motor_busqueda_web import BotJudicial
from src.ultima_gestion import (
    CAMPO_ESTADO_ULTIMA_GESTION,
    CAMPO_FECHA_ULTIMA_GESTION,
    MARCA_REVISION_ULTIMA_GESTION,
    enriquecer_ultima_gestion_judicial,
    obtener_ultima_gestion_judicial,
)


class UltimaGestionJudicialTests(unittest.TestCase):
    def test_utc_de_madrugada_corresponde_al_dia_anterior_en_ecuador(self):
        historial = [
            {
                "fecha": "2026-09-25T02:10:36.770+00:00",
                "detalle": "<p>Contenido completo de la providencia</p>",
            },
            {
                "fecha": "24/09/2026",
                "detalle": "DEVOLUCIÓN DEPRECATORIO POR CUMPLIMIENTO DE DILIGENCIA (RAZON DE NOTIFICACION)",
            },
        ]
        self.assertEqual(
            obtener_ultima_gestion_judicial(historial),
            (
                "24/09/2026",
                "DEVOLUCIÓN DEPRECATORIO POR CUMPLIMIENTO DE DILIGENCIA (RAZON DE NOTIFICACION)",
            ),
        )

    def test_solo_cuerpo_extenso_requiere_revision_manual(self):
        historial = [{
            "fecha": "2026-09-25T02:10:36.770+00:00",
            "detalle": "<p>Contenido completo de la providencia</p>",
        }]
        self.assertEqual(
            obtener_ultima_gestion_judicial(historial),
            ("24/09/2026", MARCA_REVISION_ULTIMA_GESTION),
        )

    def test_historial_ilegible_no_conserva_titulo_anterior(self):
        datos = {
            "HISTORIAL_ACTUACIONES": "{incompleto",
            CAMPO_ESTADO_ULTIMA_GESTION: "Título anterior",
        }
        enriquecer_ultima_gestion_judicial(datos)
        self.assertEqual(
            datos[CAMPO_ESTADO_ULTIMA_GESTION],
            MARCA_REVISION_ULTIMA_GESTION,
        )

    def test_revision_por_titulo_no_verificable_sale_de_para_carga(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "CODIGO_JUICIO": [1],
            "NUMERO_JUICIO": ["07331-2026-00445"],
            "COMENTARIO_ULTIMO": [""],
            "HISTORIAL_ACTUACIONES": [json.dumps([{
                "fecha": "2026-09-25T02:10:36.770+00:00",
                "detalle": "<p>Contenido completo de la providencia</p>",
            }])],
        })
        reporte, para_carga = gestor._preparar_exportacion()
        self.assertEqual(len(reporte), 1)
        self.assertTrue(para_carga.empty)
        self.assertEqual(
            reporte.loc[0, CAMPO_ESTADO_ULTIMA_GESTION],
            MARCA_REVISION_ULTIMA_GESTION,
        )
        self.assertIn("TITULO_ULTIMA_GESTION_NO_VERIFICABLE", reporte.loc[0, "COMENTARIO_ULTIMO"])

    def test_caso_referencia_prioriza_titulo_resumen_del_dia_mas_reciente(self):
        historial = [
            {
                "fecha": "2025-12-04T20:07:10.000+00:00",
                "detalle": "<p>Contenido completo del oficio</p>",
            },
            {
                "fecha": "2025-12-04T19:35:29.887+00:00",
                "detalle": "<p>Contenido de notificacion</p>",
            },
            {"fecha": "04/12/2025", "detalle": "OFICIO: (OFICIO)"},
            {
                "fecha": "04/12/2025",
                "detalle": "DISPONER CUMPLIMIENTO (AUTO DE SUSTANCIACION)",
            },
            {"fecha": "20/11/2025", "detalle": "RAZON (RAZON)"},
        ]

        self.assertEqual(
            obtener_ultima_gestion_judicial(historial),
            ("04/12/2025", "OFICIO: (OFICIO)"),
        )

    def test_acepta_historial_json_y_conserva_titulo_literal(self):
        datos = {
            "HISTORIAL_ACTUACIONES": json.dumps([
                {
                    "fecha": "2026-09-20T13:10:00Z",
                    "detalle": "AUTO DE SUSTANCIACION",
                    "titulo": "Auto de sustanciación: (Providencia)",
                },
                {"fecha": "19/09/2026", "detalle": "OFICIO (OFICIO)"},
            ], ensure_ascii=False)
        }

        enriquecer_ultima_gestion_judicial(datos)

        self.assertEqual(datos[CAMPO_FECHA_ULTIMA_GESTION], "20/09/2026")
        self.assertEqual(
            datos[CAMPO_ESTADO_ULTIMA_GESTION],
            "Auto de sustanciación: (Providencia)",
        )

    def test_api_guarda_titulo_literal_sin_cambiar_detalle_para_inferencia(self):
        actuaciones = BotJudicial._extraer_actuaciones_api([{
            "data": {
                "actuaciones": [{
                    "fecha": "04/12/2025",
                    "actuacion": "Oficio: (OFICIO)",
                }]
            }
        }])

        self.assertEqual(actuaciones[0]["detalle"], "OFICIO: (OFICIO)")
        self.assertEqual(actuaciones[0]["titulo"], "Oficio: (OFICIO)")

    def test_exportacion_coloca_campos_inmediatamente_despues_de_dias(self):
        gestor = GestorCasos.__new__(GestorCasos)
        gestor.df = pd.DataFrame({
            "NUMERO_JUICIO": ["07331-2024-00277"],
            "COMENTARIO_ULTIMO": [""],
            "FECHA_ULTIMA_GESTION_JUDICIAL": ["01/01/2000"],
            "FECHA INICIO FASE ACTUAL": ["01/12/2025"],
            "HISTORIAL_ACTUACIONES": [json.dumps([
                {"fecha": "2025-12-04T20:07:10Z", "detalle": "<p>Oficio</p>"},
                {"fecha": "04/12/2025", "detalle": "OFICIO: (OFICIO)"},
            ])],
        })

        reporte, _ = gestor._preparar_exportacion()
        indice_dias = reporte.columns.get_loc("DIAS TRANSCURRIDOS")

        self.assertEqual(
            reporte.columns[indice_dias + 1:indice_dias + 3].tolist(),
            [CAMPO_FECHA_ULTIMA_GESTION, CAMPO_ESTADO_ULTIMA_GESTION],
        )
        self.assertNotIn("FECHA_ULTIMA_GESTION_JUDICIAL", reporte.columns)
        self.assertEqual(
            reporte.loc[0, CAMPO_FECHA_ULTIMA_GESTION], "04/12/2025"
        )
        self.assertEqual(
            reporte.loc[0, CAMPO_ESTADO_ULTIMA_GESTION], "OFICIO: (OFICIO)"
        )


if __name__ == "__main__":
    unittest.main()
