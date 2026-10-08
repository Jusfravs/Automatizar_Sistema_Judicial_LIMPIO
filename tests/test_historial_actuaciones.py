"""Las actuaciones guardadas siempre tienen título (incidente de filas vacías, 8/10/2026)."""

import unittest

from src.historial_ia import normalizar_actuaciones, titulo_desde_detalle


CAUSA = "07307-2024-00904"
CARPETA = "07307202400904_1_20_12_2024_10_25_ff915488faa1"


class PruebasActuacionesConTitulo(unittest.TestCase):
    def test_descarta_actuaciones_sin_titulo_ni_detalle(self):
        resultado = normalizar_actuaciones(CAUSA, [
            {"fecha": "26/05/2025", "carpeta": CARPETA, "titulo": "", "detalle": ""},
            {"fecha": "26/05/2025", "carpeta": CARPETA, "titulo": "   ", "detalle": None},
        ])
        self.assertEqual(resultado, [])

    def test_conserva_las_que_tienen_titulo(self):
        resultado = normalizar_actuaciones(CAUSA, [
            {"fecha": "26/05/2025", "carpeta": CARPETA, "titulo": "CITACIÓN: No realizada", "detalle": ""},
        ])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["titulo"], "CITACIÓN: No realizada")

    def test_solo_detalle_recibe_su_primera_linea_como_titulo(self):
        detalle = '<P STYLE="TEXT-ALIGN: JUSTIFY;">ACTA DE CITACI&Oacute;N</P><BR><P>Texto completo...</P>'
        resultado = normalizar_actuaciones(CAUSA, [
            {"fecha": "2025-05-26T16:38:48.000+00:00", "carpeta": CARPETA, "titulo": "", "detalle": detalle},
        ])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["titulo"], "ACTA DE CITACIÓN")
        self.assertEqual(resultado[0]["detalle"], detalle)

    def test_la_identidad_no_cambia_al_derivar_el_titulo(self):
        """El ID se calcula con el contenido original: lo ya guardado no se duplica."""
        original = {"fecha": "2025-05-26", "carpeta": CARPETA, "titulo": "", "detalle": "ESCRITO, FEPRESENTACION"}
        resultado = normalizar_actuaciones(CAUSA, [original])
        import hashlib, json
        contenido = {"causa": CAUSA, "carpeta": CARPETA, "fecha": "2025-05-26", "titulo": "",
                     "detalle": "ESCRITO, FEPRESENTACION"}
        huella = hashlib.sha256(json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(resultado[0]["actuacion_id"], "ACT-" + huella[:24])
        self.assertEqual(resultado[0]["titulo"], "ESCRITO, FEPRESENTACION")

    def test_titulo_derivado_se_recorta(self):
        largo = "VISTOS " + "palabra " * 60
        titulo = titulo_desde_detalle(largo)
        self.assertLessEqual(len(titulo), 160)
        self.assertTrue(titulo.endswith("…"))

    def test_detalle_solo_con_etiquetas_se_descarta(self):
        resultado = normalizar_actuaciones(CAUSA, [
            {"fecha": "26/05/2025", "carpeta": CARPETA, "titulo": "", "detalle": "<p></p><br>"},
        ])
        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()
