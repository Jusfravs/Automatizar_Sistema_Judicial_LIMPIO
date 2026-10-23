import unittest
from collections import Counter
from unittest.mock import patch

from scripts.recalcular_condicion import _condicion, _historial_guardado
from src.agente_extractor import MotorInferenciaProcesal


class TestRecalcularCondicion(unittest.TestCase):

    def test_causa_sin_actuaciones_queda_por_confirmar(self):
        resumen = Counter()
        nueva = _condicion([], "17230-2024-00001", {"datos": {}}, resumen)
        self.assertEqual(nueva["CONDICION"], "POR_CONFIRMAR")
        self.assertIsNone(nueva["ACTUACION CONDICION"])
        self.assertEqual(resumen["sin_historial"], 1)
        self.assertEqual(resumen["sin_actuaciones"], 1)

    def test_causa_sin_etapa_queda_por_confirmar(self):
        resumen = Counter()
        filas = [("a1", "01/02/2024", "ESCRITO", "ESCRITO", "PRINCIPAL")]
        with patch.object(MotorInferenciaProcesal, "inferir_estado_procesal",
                          return_value={"ULTIMA_ETAPA": None}):
            nueva = _condicion(filas, "17230-2024-00002", None, resumen)
        self.assertEqual(nueva["CONDICION"], "POR_CONFIRMAR")
        self.assertEqual(resumen["sin_historial"], 1)
        self.assertEqual(resumen["sin_etapa"], 1)

    def test_respaldo_compactado_une_el_auto_con_su_cuerpo(self):
        # El histórico guardó el rótulo del auto sin texto y su cuerpo HTML como
        # otra fila del mismo día, con fecha ISO y un "título" que es el HTML.
        cuerpo = ("<p><strong>VISTOS:</strong> EN LO PRINCIPAL, SE DECLARA EL ABANDONO "
                  "DE LA INSTANCIA Y EL ARCHIVO DE LA CAUSA.</p>")
        filas = [
            ("a1", "01/02/2024", "INGRESO DE CAUSA", "INGRESO DE CAUSA", "PRINCIPAL"),
            ("a2", "10/02/2024", "AUTO DE CALIFICACION", "AUTO DE CALIFICACION, CITESE", "PRINCIPAL"),
            ("a3", "05/09/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", "PRINCIPAL"),
            ("a4", "2025-09-05T15:44:56.000+00:00", "", "", "PRINCIPAL"),
        ]

        class Respaldo:
            def execute(self, _sql, _params):
                return [("a4", cuerpo[:80], cuerpo)]

        historial = _historial_guardado(filas, "17230-2024-00004", Respaldo())
        auto = historial[2]
        self.assertEqual(historial[3]["fecha"], "05/09/2025")
        self.assertEqual(historial[3]["titulo"], "")
        self.assertNotIn("<", auto["detalle"])
        self.assertIn("SE DECLARA EL ABANDONO", auto["detalle"])
        resultado = MotorInferenciaProcesal.inferir_estado_procesal(historial)
        self.assertEqual(resultado.get("CONDICION"), "ABANDONADA")

    def test_razon_de_notificacion_no_recibe_el_cuerpo(self):
        filas = [
            ("a1", "05/09/2025", "ABANDONO (RAZON DE NOTIFICACION)", "", "PRINCIPAL"),
            ("a2", "05/09/2025", "", "SE DECLARA EL ABANDONO", "PRINCIPAL"),
        ]
        historial = _historial_guardado(filas, "17230-2024-00005")
        self.assertEqual(historial[0]["detalle"], "ABANDONO (RAZON DE NOTIFICACION)")

    def test_causa_con_etapa_conserva_la_condicion_del_motor(self):
        resumen = Counter()
        filas = [("a1", "01/02/2024", "AUTO DE CALIFICACION", "CITESE", "PRINCIPAL")]
        with patch.object(MotorInferenciaProcesal, "inferir_estado_procesal",
                          return_value={"ULTIMA_ETAPA": "1", "CONDICION": "CONCLUIDA",
                                        "FECHA_CONDICION": "01/02/2024",
                                        "ACTUACION_CONDICION": "a1"}):
            nueva = _condicion(filas, "17230-2024-00003", None, resumen)
        self.assertEqual(nueva["CONDICION"], "CONCLUIDA")
        self.assertEqual(resumen["sin_historial"], 0)


if __name__ == "__main__":
    unittest.main()
