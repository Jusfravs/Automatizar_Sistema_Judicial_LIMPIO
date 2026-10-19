import unittest

from src.agente_extractor import MotorInferenciaProcesal


def inferir(actuaciones):
    return MotorInferenciaProcesal.inferir_estado_procesal(actuaciones)


BASE = [
    {"fecha": "01/02/2024", "titulo": "INGRESO DE CAUSA", "detalle": "INGRESO DE CAUSA"},
    {"fecha": "10/02/2024", "titulo": "AUTO DE CALIFICACION", "detalle": "AUTO DE CALIFICACION, CITESE A LA PARTE DEMANDADA"},
]


class TestCondicionCausa(unittest.TestCase):
    """La condición es un eje aparte de la etapa y la fase."""

    def test_sin_cierre_es_vigente(self):
        r = inferir(BASE)
        self.assertEqual(r.get("CONDICION"), "VIGENTE")
        self.assertIsNone(r.get("FECHA_CONDICION"))

    def test_envio_al_archivo_general_sigue_vigente(self):
        r = inferir(BASE + [{
            "fecha": "01/06/2024",
            "titulo": "ENVIO DEL PROCESO AL ARCHIVO GENERAL (RAZON)",
            "detalle": "RAZON: SE REMITE EL PROCESO AL DEPARTAMENTO DE ARCHIVO, HASTA QUE SE REALICE EL IMPULSO PROCESAL RESPECTIVO",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_abandono_por_falta_de_impulso(self):
        r = inferir(BASE + [
            {"fecha": "05/09/2025", "titulo": "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO)",
             "detalle": "SE DECLARA EL ABANDONO DE LA CAUSA"},
            {"fecha": "05/09/2025", "titulo": "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (RAZON DE NOTIFICACION)",
             "detalle": "RAZON DE NOTIFICACION"},
        ])
        self.assertEqual(r.get("CONDICION"), "ABANDONADA")
        self.assertEqual(r.get("FECHA_CONDICION"), "05/09/2025")
        # La fase actual se conserva para retomarla si se reactiva.
        self.assertTrue(r.get("FASE_ACTUAL"))

    def test_archivo_por_no_completar_demanda(self):
        r = inferir(BASE[:1] + [{
            "fecha": "20/02/2024", "titulo": "ARCHIVO POR NO COMPLETAR DEMANDA (AUTO INTERLOCUTORIO)",
            "detalle": "ARCHIVO POR NO COMPLETAR DEMANDA",
        }])
        self.assertEqual(r.get("CONDICION"), "ARCHIVADA")

    def test_acuerdo_transaccional_concluye(self):
        r = inferir(BASE + [{
            "fecha": "15/03/2025", "titulo": "ACUERDO TRANSACCIONAL (AUTO INTERLOCUTORIO)",
            "detalle": "SE APRUEBA EL ACUERDO TRANSACCIONAL",
        }])
        self.assertEqual(r.get("CONDICION"), "CONCLUIDA")

    def test_derivacion_a_mediacion_no_concluye(self):
        r = inferir(BASE + [{
            "fecha": "15/03/2025", "titulo": "DERIVACION A MEDIACION (AUTO INTERLOCUTORIO)",
            "detalle": "SE DERIVA LA CAUSA AL CENTRO DE MEDIACION",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_nulidad_posterior_reactiva(self):
        r = inferir(BASE + [
            {"fecha": "05/09/2025", "titulo": "ABANDONO (AUTO RESOLUTIVO)", "detalle": "ABANDONO"},
            {"fecha": "20/10/2025", "titulo": "NULIDAD PROCESAL DECLARADA DE OFICIO ART. 110 (AUTO INTERLOCUTORIO)",
             "detalle": "SE DECLARA LA NULIDAD"},
        ])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_nulidad_anterior_no_reactiva(self):
        r = inferir(BASE + [
            {"fecha": "20/05/2025", "titulo": "NULIDAD POR FALTA DE CITACION (AUTO INTERLOCUTORIO)", "detalle": "NULIDAD"},
            {"fecha": "05/09/2025", "titulo": "ABANDONO (AUTO RESOLUTIVO)", "detalle": "ABANDONO"},
        ])
        self.assertEqual(r.get("CONDICION"), "ABANDONADA")

    def test_archivo_de_deprecatorio_no_archiva_la_causa(self):
        r = inferir(BASE + [{
            "fecha": "05/09/2025", "titulo": "ARCHIVO DE LA CAUSA (AUTO RESOLUTIVO)", "detalle": "ARCHIVESE",
            "ORIGEN_CARPETA": "CARATULA SORTEO DE DEPRECATORIOS",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_remate_concluye(self):
        r = inferir(BASE + [
            {"fecha": "10/03/2024", "titulo": "MANDAMIENTO DE EJECUCION", "detalle": "MANDAMIENTO DE EJECUCION"},
            {"fecha": "10/06/2025", "titulo": "AUTO DE ADJUDICACION", "detalle": "AUTO DE ADJUDICACION DEL REMATE"},
        ])
        self.assertEqual(r.get("MENSAJE_ESPECIAL"), "CASO SOLVENTADO POR REMATE")
        self.assertEqual(r.get("CONDICION"), "CONCLUIDA")
        self.assertEqual(r.get("FECHA_CONDICION"), "10/06/2025")

    def test_nulidad_de_remate_posterior_reactiva(self):
        r = inferir(BASE + [
            {"fecha": "10/03/2024", "titulo": "MANDAMIENTO DE EJECUCION", "detalle": "MANDAMIENTO DE EJECUCION"},
            {"fecha": "10/06/2025", "titulo": "AUTO DE ADJUDICACION", "detalle": "AUTO DE ADJUDICACION DEL REMATE"},
            {"fecha": "20/06/2025", "titulo": "NULIDAD DE REMATE (AUTO INTERLOCUTORIO)", "detalle": "SE DECLARA LA NULIDAD DEL REMATE"},
        ])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_solicitud_de_abandono_no_cierra(self):
        r = inferir(BASE + [{
            "fecha": "05/09/2025", "titulo": "ESCRITO",
            "detalle": "ABANDONO DE LA CAUSA SOLICITADO POR LA DEMANDADA",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_rotulo_sin_tipo_de_auto_no_cierra(self):
        r = inferir(BASE + [{
            "fecha": "05/09/2025", "detalle": "ABANDONO DE LA CAUSA SOLICITADO POR LA DEMANDADA",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_auto_que_niega_el_abandono_no_cierra(self):
        r = inferir(BASE + [{
            "fecha": "05/09/2025", "titulo": "ABANDONO (AUTO RESOLUTIVO)",
            "detalle": "SE NIEGA EL PEDIDO DE ABANDONO POR CUANTO EXISTE IMPULSO DE LA PARTE ACTORA",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_nulidad_negada_no_reactiva(self):
        r = inferir(BASE + [
            {"fecha": "05/09/2025", "titulo": "ABANDONO (AUTO RESOLUTIVO)", "detalle": "SE DECLARA EL ABANDONO"},
            {"fecha": "20/10/2025", "titulo": "NULIDAD PROCESAL DECLARADA DE OFICIO ART. 110 (AUTO INTERLOCUTORIO)",
             "detalle": "SE NIEGA LA NULIDAD SOLICITADA"},
        ])
        self.assertEqual(r.get("CONDICION"), "ABANDONADA")

    def test_inhibicion_no_archiva(self):
        r = inferir(BASE + [{
            "fecha": "05/09/2025", "titulo": "INHIBICION (AUTO INTERLOCUTORIO)",
            "detalle": "EL JUEZ SE INHIBE Y REMITE LA CAUSA AL COMPETENTE",
        }])
        self.assertEqual(r.get("CONDICION"), "VIGENTE")

    def test_rotulo_dom_con_cuerpo_cierra(self):
        # En la ruta DOM el título es la fila completa: rótulo y cuerpo juntos.
        texto = "ABANDONO POR FALTA DE IMPULSO PROCESAL ART. 245 (AUTO INTERLOCUTORIO) VISTOS: SE DECLARA EL ABANDONO"
        r = inferir(BASE + [{"fecha": "05/09/2025", "titulo": texto, "detalle": texto}])
        self.assertEqual(r.get("CONDICION"), "ABANDONADA")

    def test_cierre_no_altera_etapa_ni_fase(self):
        sin = inferir(BASE)
        con = inferir(BASE + [{"fecha": "05/09/2025", "titulo": "ABANDONO (AUTO RESOLUTIVO)", "detalle": "ABANDONO"}])
        self.assertEqual(con.get("ULTIMA_FASE"), sin.get("ULTIMA_FASE"))


if __name__ == "__main__":
    unittest.main()
