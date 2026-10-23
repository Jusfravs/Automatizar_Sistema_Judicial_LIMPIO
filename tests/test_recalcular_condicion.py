import unittest
from collections import Counter
from unittest.mock import patch

from scripts.recalcular_condicion import (
    _condicion, _historial_guardado, _metadatos, _sin_decision,
)
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

    def test_dos_autos_y_dos_cuerpos_del_mismo_dia_no_se_unen(self):
        resumen = Counter()
        filas = [
            ("a1", "05/09/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", "PRINCIPAL"),
            ("a2", "05/09/2025", "NULIDAD PROCESAL (AUTO INTERLOCUTORIO)", "", "PRINCIPAL"),
            ("a3", "05/09/2025", "", "VISTOS: SE DECLARA EL ABANDONO", "PRINCIPAL"),
            ("a4", "05/09/2025", "", "VISTOS: SE DECLARA LA NULIDAD", "PRINCIPAL"),
        ]
        historial = _historial_guardado(filas, "17230-2024-00006", resumen=resumen)
        self.assertEqual(historial[0]["detalle"], historial[0]["titulo"])
        self.assertEqual(historial[1]["detalle"], historial[1]["titulo"])
        self.assertEqual(resumen["cuerpos_ambiguos"], 1)

    def test_no_se_une_el_cuerpo_de_otra_carpeta(self):
        filas = [
            ("a1", "05/09/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", "PRINCIPAL"),
            ("a2", "05/09/2025", "", "VISTOS: SE DECLARA EL ABANDONO", "DEPRECATORIO 1"),
        ]
        historial = _historial_guardado(filas, "17230-2024-00007")
        self.assertNotIn("SE DECLARA", historial[0]["detalle"])

    def test_historial_inline_con_rotulos_no_tapa_el_respaldo(self):
        resumen = Counter()
        filas = [
            ("a1", "01/02/2024", "INGRESO DE CAUSA", "INGRESO DE CAUSA", "PRINCIPAL"),
            ("a2", "10/02/2024", "AUTO DE CALIFICACION", "AUTO DE CALIFICACION, CITESE", "PRINCIPAL"),
            ("a3", "05/09/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", "PRINCIPAL"),
            ("a4", "05/09/2025", "", "VISTOS: SE DECLARA EL ABANDONO DE LA INSTANCIA", "PRINCIPAL"),
        ]
        payload = {"datos": {"HISTORIAL_ACTUACIONES": [
            {"fecha": f[1], "titulo": f[2], "detalle": f[2]} for f in filas[:3]
        ]}}
        nueva = _condicion(filas, "17230-2024-00008", payload, resumen)
        self.assertEqual(nueva["CONDICION"], "ABANDONADA")
        self.assertEqual(resumen["fuente_historial"], 1)
        self.assertEqual(resumen["inline_descartado"], 1)

    def test_metadatos_nuevos_cuentan_como_cambio(self):
        guardado = ("POR_CONFIRMAR", None, None)
        nueva = {"CONDICION": "POR_CONFIRMAR", "FECHA CONDICION": "05/09/2025",
                 "ACTUACION CONDICION": "ABANDONO (AUTO INTERLOCUTORIO)"}
        self.assertNotEqual(_metadatos(nueva), guardado)
        self.assertEqual(_metadatos(_sin_decision()), guardado)

    def test_razon_y_notificacion_del_dia_no_son_cuerpo_del_auto(self):
        # Así está en el respaldo: copias de rótulos, la razón del secretario,
        # el auto y la notificación, todos el mismo día y en la misma carpeta.
        rotulo = "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)"
        filas = [
            ("a1", "15/12/2025", rotulo, "", "C1"),
            ("a2", "15/12/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (RAZON DE NOTIFICACION)", "", "C1"),
            ("a3", "15/12/2025", "", rotulo, "C1"),
            ("a4", "2025-12-15T13:27:16", "", "RAZON: SIENTO POR TAL QUE DESDE LA ULTIMA ACTUACION", "C1"),
            ("a5", "2025-12-15T15:44:56", "", "VISTOS: EN LO PRINCIPAL, SE DECLARA EL ABANDONO", "C1"),
            ("a6", "2025-12-15T19:27:08", "", "EN QUITO, LUNES QUINCE DE DICIEMBRE, NOTIFICO", "C1"),
        ]
        historial = _historial_guardado(filas, "17230-2024-00009")
        self.assertIn("SE DECLARA EL ABANDONO", historial[0]["detalle"])
        self.assertNotIn("SE DECLARA", historial[1]["detalle"])

    def test_auto_con_rotulo_de_razon_en_el_respaldo_recibe_su_cuerpo(self):
        filas = [
            ("a1", "08/04/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", "C1"),
            ("a2", "2025-04-08T21:32:53", "", "", "C1"),
        ]

        class Respaldo:
            def execute(self, _sql, _params):
                return [("a1", "", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (RAZON DE NOTIFICACION)"),
                        ("a2", "", "VISTOS: SE DECLARA EL ABANDONO DE LA INSTANCIA")]

        historial = _historial_guardado(filas, "17230-2024-00010", Respaldo())
        self.assertIn("SE DECLARA EL ABANDONO", historial[0]["detalle"])

    def test_capturas_distintas_del_mismo_cuaderno_se_unen(self):
        cuaderno = "17233201905759_1_01_10_2019_15_38_"
        filas = [
            ("a1", "08/04/2025", "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "", cuaderno + "6eaedf66fea7"),
            ("a2", "2025-04-08T21:32:53", "<p>VISTOS: SE DECLARA EL ABANDONO", "", cuaderno + "6eaedf66fea7"),
            ("a3", "2025-04-08T21:32:53", "", "VISTOS: SE DECLARA EL ABANDONO", cuaderno + "331850de943f"),
        ]
        historial = _historial_guardado(filas, "17230-2024-00011")
        self.assertIn("SE DECLARA EL ABANDONO", historial[0]["detalle"])
        self.assertEqual(historial[1]["titulo"], "")

    def test_razon_de_notificacion_no_recibe_el_cuerpo(self):
        filas = [
            ("a1", "05/09/2025", "ABANDONO (RAZON DE NOTIFICACION)", "", "PRINCIPAL"),
            ("a2", "05/09/2025", "", "VISTOS: SE DECLARA EL ABANDONO", "PRINCIPAL"),
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
