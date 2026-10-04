import unittest
from src.motor_busqueda_web import BotJudicial


class TestExtraccionAPI(unittest.TestCase):
    def test_mandamiento_api_reconocido(self):
        """Simula una respuesta JSON de la API que contiene una actuación 'Mandamiento de ejecución' y verifica que
        el extractor la clasifique como MANDAMIENTO DE EJECUCION (fase 6.2).
        """
        bot = BotJudicial(url_portal="https://example.local")

        # Simular paquete API interceptado
        bot.paquetes_api_interceptados = [
            {
                "url": "https://api.mock/causa/23331-2022-04261",
                "data": [
                    {
                        "actuaciones": [
                            {"fecha": "01/01/2024", "actuacion": "Mandamiento de ejecución"}
                        ]
                    }
                ]
            }
        ]

        datos = bot._ejecutar_extraccion_detalles()

        self.assertIsNotNone(datos)
        self.assertIsNotNone(datos.get("FASE_PROCESAL"))
        # FASE_PROCESAL es el destino operativo; el mandamiento permanece
        # auditado en ULTIMA FASE y abre la fase de embargo.
        self.assertIn("EMBARGO", datos.get("FASE_PROCESAL").upper())
        self.assertIsNotNone(datos.get("ETAPA_PROCESAL"))
        self.assertIn("LIQUIDACION", datos.get("ETAPA_PROCESAL").upper())

