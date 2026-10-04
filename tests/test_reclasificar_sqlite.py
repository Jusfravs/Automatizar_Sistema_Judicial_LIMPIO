import unittest

import pandas as pd

from scripts.reclasificar_desde_sqlite import (
    _reclasificar_datos,
    _reporte_tiene_revision_manual_automatica,
)


class TestReclasificarDesdeSQLite(unittest.TestCase):
    def test_limpia_revision_manual_automatica_si_citacion_es_siguiente_paso(self):
        datos = {
            "COMENTARIO_ULTIMO": "REVISION MANUAL",
            "HISTORIAL_ACTUACIONES": [
                {
                    "fecha": "16/09/2015",
                    "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
                },
                {
                    "fecha": "05/06/2017",
                    "detalle": (
                        "EL ACTOR NO HA PROPORCIONADO LAS COPIAS PERTINENTES PARA "
                        "REALIZAR LA CITACION. NO SE HA TRABADO LA LITIS. "
                        "SE ORDENA EL ARCHIVO DE LA PRESENTE CAUSA."
                    ),
                },
            ],
        }

        _, nuevos = _reclasificar_datos(datos, causa="17230-2015-13845")

        self.assertEqual(nuevos["ETAPA ACTUAL"], "2 CITACION")
        self.assertEqual(nuevos["FASE ACTUAL"], "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(nuevos["COMENTARIO_ULTIMO"], "")
        self.assertIsNone(datos["COMENTARIO_ULTIMO"])

    def test_limpia_marca_automatica_de_remate_tras_reclasificar(self):
        datos = {
            'COMENTARIO_ULTIMO': 'CASO SOLVENTADO POR REMATE',
            'HISTORIAL_ACTUACIONES': [
                {'fecha': '28/11/2017', 'detalle': 'MANDAMIENTO DE EJECUCION (AUTO)'},
                {'fecha': '12/12/2017', 'detalle': 'SE PRETENDE EMBARGAR UN VEHICULO; NO SE ATIENDE LO PETICIONADO POR IMPROCEDENTE.'},
            ],
        }

        _, nuevos = _reclasificar_datos(datos, causa='07333-2015-02213')

        self.assertEqual(nuevos['ULTIMA FASE'], '6.2 MANDAMIENTO DE EJECUCION')
        self.assertEqual(nuevos['COMENTARIO_ULTIMO'], '')
        self.assertIsNone(datos['COMENTARIO_ULTIMO'])

    def test_detecta_solo_la_marca_automatica_exacta_en_reporte(self):
        class Repo:
            df = pd.DataFrame({
                "NUMERO_JUICIO": ["17230-2015-13845", "17233-2024-07607"],
                "COMENTARIO_ULTIMO": ["REVISION MANUAL", "por citar"],
            })

        self.assertTrue(
            _reporte_tiene_revision_manual_automatica(Repo(), "17230-2015-13845")
        )
        self.assertFalse(
            _reporte_tiene_revision_manual_automatica(Repo(), "17233-2024-07607")
        )

    def test_persiste_revision_documental_y_limpia_marca_si_desaparece_evidencia(self):
        datos = {
            "HISTORIAL_ACTUACIONES": [
                {
                    "fecha": "15/08/2022",
                    "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
                },
                {
                    "fecha": "16/12/2022",
                    "detalle": "ESCRITO, FEPRESENTACION",
                    "TIENE_ADJUNTO": True,
                },
            ],
        }

        _, nuevos = _reclasificar_datos(datos, causa="07333-2022-01899")

        self.assertEqual(nuevos["ULTIMA FASE"], "1.3 CALIFICACION")
        self.assertEqual(nuevos["FASE ACTUAL"], "REVISION MANUAL")
        self.assertIn("ESCRITO POSTERIOR SIN TIPO CONFIRMADO", nuevos["COMENTARIO_ULTIMO"])

        datos["HISTORIAL_ACTUACIONES"][-1].pop("TIENE_ADJUNTO")
        _, nuevos_sin_adjunto = _reclasificar_datos(
            datos, causa="07333-2022-01899"
        )
        self.assertEqual(nuevos_sin_adjunto["FASE ACTUAL"], "2.1 CITACION (PERSONA/BOLETA)")
        self.assertEqual(nuevos_sin_adjunto["COMENTARIO_ULTIMO"], "")
