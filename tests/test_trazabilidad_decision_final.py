"""Pruebas de trazabilidad para evitar confundir inferencias DOM con finales."""

import json
import unittest
from unittest.mock import patch

from src.motor_busqueda_web import BotJudicial


class TestTrazabilidadDecisionFinal(unittest.TestCase):
    def test_inferencia_consolidada_registra_decision_final_de_causa(self):
        bot = BotJudicial(url_portal="https://example.local")
        datos = {
            "ORIGEN_DATA": "API+DOM",
            "HISTORIAL_ACTUACIONES": [
                {
                    "fecha": "08/07/2026",
                    "detalle": "PUBLICACION Y FECHA PARA REMATE (AUTO INTERLOCUTORIO)",
                }
            ],
        }

        with patch("src.motor_busqueda_web.logger.info") as info:
            bot._aplicar_inferencia_consolidada(
                datos, causa="07333-2019-00278", alcance="causa"
            )

        llamadas_finales = [
            llamada for llamada in info.call_args_list
            if llamada.args and llamada.args[0] == "[DECISION_FASE_FINAL] %s"
        ]
        self.assertEqual(len(llamadas_finales), 1)
        payload = json.loads(llamadas_finales[0].args[1])
        self.assertEqual(payload["estado_decision"], "FINAL")
        self.assertEqual(payload["alcance"], "causa")
        self.assertEqual(payload["causa"], "07333201900278")
        self.assertEqual(payload["fase_deducida"], datos["ULTIMA FASE"])
        self.assertEqual(payload["fecha_final"], datos["FECHA FIN ULTIMA FASE"])
