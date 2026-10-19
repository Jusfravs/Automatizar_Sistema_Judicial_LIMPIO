"""Inferencia NVIDIA independiente: privacidad, catálogo y fallos controlados."""

import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from src.proveedor_nvidia import (
    ControlInferenciaIA, ErrorAuditoriaIA, anonimizar_texto,
    construir_contexto_inferencia, inferir_nvidia, siguiente_estado_arbol,
    validar_inferencia,
)
from src.motor_busqueda_web import BotJudicial
from src.inferencia_dual import aplicar_jerarquia, comparar, huella_motor
from scripts.comparar_inferencias import evaluar, redactar_reporte, seudonimo


class InferenciaDualTests(unittest.TestCase):
    def setUp(self):
        self.datos = {
            "ACTOR": "JUAN PEREZ", "DEMANDADO": "ANA LOPEZ",
            "ETAPA ACTUAL": "6 LIQUIDACION Y EMBARGO",
            "FASE ACTUAL": "6.3 EMBARGO",
            "HISTORIAL_ACTUACIONES": [{
                "actuacion_id": "hito-1", "fecha": "01/01/2026",
                "titulo": "AUTO DE CITACION", "detalle": (
                    "Citación a JUAN PEREZ y ANA LOPEZ, cédula 1712345678, "
                    "correo juan@example.com, teléfono 0991234567, casillero 1234."
                ),
            }],
        }
        self.contexto, self.mapa = construir_contexto_inferencia(
            self.datos, self.datos["HISTORIAL_ACTUACIONES"]
        )
        self.decision = {
            "ultimo_hito": {"eta_id": 10, "fas_id": 79},
            "evidencias": ["A1"], "confianza": 0.91,
            "motivo": "Auto de citación", "requiere_revision_humana": False,
        }

    def test_contexto_es_ciego_y_texto_es_opcional(self):
        serializado = json.dumps(self.contexto, ensure_ascii=False)
        self.assertNotIn("inferencia_sistema", serializado)
        self.assertNotIn("lectura_temporal", serializado)
        self.assertNotIn("JUAN PEREZ", serializado)
        self.assertNotIn('"inferencia_sistema"', serializado)
        self.assertEqual(self.contexto["cronologia"][0]["senales"], ["CITACION"])
        con_texto, _ = construir_contexto_inferencia(
            self.datos, self.datos["HISTORIAL_ACTUACIONES"], incluir_texto=True
        )
        texto = con_texto["cronologia"][0]["texto"]
        for privado in ("JUAN PEREZ", "ANA LOPEZ", "1712345678", "juan@example.com",
                        "0991234567", "casillero 1234"):
            self.assertNotIn(privado, texto)
        self.assertIn("Citación", texto)
        self.assertLessEqual(len(texto), 600)

    def test_contexto_distingue_citacion_fallida_y_sentencia_citada(self):
        actuaciones = [
            {"actuacion_id": "a1", "fecha": "01/01/2025", "titulo": "AUTO",
             "detalle": "SE PRONUNCIARA INMEDIATAMENTE SENTENCIA"},
            {"actuacion_id": "a2", "fecha": "02/01/2025", "titulo": "PROVIDENCIA",
             "detalle": "SEGUN SENTENCIA NRO. 123 DE LA CORTE CONSTITUCIONAL"},
            {"actuacion_id": "a3", "fecha": "03/01/2025", "titulo": "CITACION",
             "detalle": "CITACION: NO REALIZADA - DESCONOCIDO"},
            {"actuacion_id": "a4", "fecha": "04/01/2025", "titulo": "ACTA DE CITACION",
             "detalle": "ACTA DE CITACION"},
            {"actuacion_id": "a5", "fecha": "05/01/2025", "titulo": "CITACION",
             "detalle": "CITACION: REALIZADA - EN PERSONA"},
        ]
        contexto, _ = construir_contexto_inferencia({}, actuaciones)
        cronologia = contexto["cronologia"]
        self.assertNotIn("SENTENCIA", cronologia[0]["tipo"])
        self.assertNotIn("SENTENCIA", cronologia[1]["tipo"])
        self.assertEqual([p["citacion"]["resultado"] for p in cronologia[2:]], [
            "NO_REALIZADA", "SIN_CONSTANCIA", "REALIZADA",
        ])

    def test_contexto_conserva_mandamiento_intermedio_fuera_del_recorte(self):
        actuaciones = [
            {"actuacion_id": str(i),
             "fecha": f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
             "titulo": "OFICIO", "detalle": "OFICIO"}
            for i in range(120)
        ]
        actuaciones[20] = {
            "actuacion_id": "20", "fecha": "2025-01-21",
            "titulo": "MANDAMIENTO DE EJECUCION",
            "detalle": "MANDAMIENTO DE EJECUCION (AUTO INTERLOCUTORIO)",
        }
        contexto, mapa = construir_contexto_inferencia({}, actuaciones)
        self.assertEqual(len(contexto["cronologia"]), 100)
        self.assertIn("20", {act["actuacion_id"] for act in mapa.values()})

    def test_anonimiza_causa_y_limita_total(self):
        self.assertNotIn("07331-2024-00277", anonimizar_texto("causa 07331-2024-00277"))
        datos = dict(self.datos)
        datos["HISTORIAL_ACTUACIONES"] = [
            {"actuacion_id": str(i), "fecha": "01/01/2026", "detalle": "A" * 1000}
            for i in range(50)
        ]
        contexto, _ = construir_contexto_inferencia(
            datos, datos["HISTORIAL_ACTUACIONES"], incluir_texto=True
        )
        self.assertLessEqual(sum(len(x.get("texto", "")) for x in contexto["cronologia"]), 12000)

    def test_valida_pares_evidencias_y_insuficiente(self):
        validada = validar_inferencia(self.decision, self.mapa)
        self.assertEqual(validada["evidencias"], ["hito-1"])
        self.assertEqual(validada["estado_actual"], {"eta_id": 11, "fas_id": 80})
        for cambio in (
            {"evidencias": ["A999"]},
            {"ultimo_hito": {"eta_id": 12, "fas_id": 80}},
            {"ultimo_hito": {"eta_id": 2, "fas_id": 80}},
            {"confianza": 1.1},
            {"evidencias": []},
        ):
            with self.subTest(cambio=cambio), self.assertRaises(ErrorAuditoriaIA):
                validar_inferencia({**self.decision, **cambio}, self.mapa)
        insuficiente = {**self.decision, "ultimo_hito": None, "evidencias": [],
                        "requiere_revision_humana": True}
        self.assertEqual(validar_inferencia(insuficiente, self.mapa)["estado"], "INSUFICIENTE")

    def test_mandamiento_exige_actuacion_que_lo_acredite(self):
        actuaciones = [{"actuacion_id": "r1", "fecha": "02/10/2025",
                        "titulo": "RAZON DE EJECUTORIA",
                        "detalle": "RAZON DE EJECUTORIA (RAZON)"}]
        contexto, mapa = construir_contexto_inferencia({}, actuaciones)
        propuesta = {**self.decision,
                     "ultimo_hito": {"eta_id": 15, "fas_id": 89}}
        with self.assertRaisesRegex(ErrorAuditoriaIA, "MANDAMIENTO_SIN_EVIDENCIA"):
            validar_inferencia(propuesta, mapa, contexto)

    def test_citacion_de_un_demandado_no_resuelve_fallo_de_otro(self):
        actuaciones = [
            {"actuacion_id": "r1", "detalle": "CITACION: REALIZADA - EN PERSONA"},
            {"actuacion_id": "r2", "detalle": "CITACION: NO REALIZADA - DESCONOCIDO"},
        ]
        contexto = {"cronologia": [
            {"ref": "A1", "fecha": "2026-09-18", "carpeta": "C1",
             "citacion": {"resultado": "REALIZADA", "persona": "P1"}},
            {"ref": "A2", "fecha": "2026-09-23", "carpeta": "C1",
             "citacion": {"resultado": "NO_REALIZADA", "persona": "P2"}},
        ]}
        propuesta = {**self.decision,
                     "ultimo_hito": {"eta_id": 11, "fas_id": 80}}
        with self.assertRaisesRegex(ErrorAuditoriaIA, "CITACION_PENDIENTE_OTRA_PERSONA"):
            validar_inferencia(propuesta, {"A1": actuaciones[0], "A2": actuaciones[1]},
                               contexto)

    def test_archivo_posterior_a_evidencia_exige_revision(self):
        actuaciones = [
            {"actuacion_id": "r1", "detalle": "AUTO DE CALIFICACION"},
            {"actuacion_id": "r2", "detalle": "SE REMITE AL ARCHIVO GENERAL"},
        ]
        contexto = {"cronologia": [
            {"ref": "A1", "fecha": "2025-01-01", "carpeta": "C1"},
            {"ref": "A2", "fecha": "2025-02-01", "carpeta": "C1",
             "cierre": "ARCHIVO_PASIVO"},
        ]}
        with self.assertRaisesRegex(ErrorAuditoriaIA, "CIERRE_POSTERIOR_A_HITO"):
            validar_inferencia(self.decision,
                               {"A1": actuaciones[0], "A2": actuaciones[1]}, contexto)

    def test_actual_es_siguiente_del_ultimo_hito_y_no_respuesta_ia(self):
        for ultimo, siguiente in (
            ((10, 79), (11, 80)),
            ((11, 80), (12, 82)),
            ((15, 89), (15, 90)),
            ((15, 90), (15, 91)),
            ((15, 91), (15, 91)),
            ((15, 92), (15, 92)),
        ):
            with self.subTest(ultimo=ultimo):
                hito = {"eta_id": ultimo[0], "fas_id": ultimo[1]}
                self.assertEqual(
                    siguiente_estado_arbol(hito),
                    {"eta_id": siguiente[0], "fas_id": siguiente[1]},
                )
                propuesta = {**self.decision, "ultimo_hito": hito,
                             "estado_actual": hito}
                validada = validar_inferencia(propuesta, self.mapa)
                self.assertEqual(validada["estado_actual"],
                                 {"eta_id": siguiente[0], "fas_id": siguiente[1]})

    def test_transporte_simulado_y_circuito(self):
        respuesta = {"choices": [{"message": {"content": json.dumps(self.decision)}}],
                     "usage": {"total_tokens": 40}}
        control = ControlInferenciaIA()
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "clave-de-prueba"}), \
             patch("src.proveedor_nvidia.urlopen", return_value=io.BytesIO(
                 json.dumps(respuesta).encode("utf-8"))):
            decision, uso = inferir_nvidia(self.contexto, self.mapa, control=control)
        self.assertEqual(decision["estado_actual"]["fas_id"], 80)
        self.assertEqual(uso["total_tokens"], 40)
        self.assertFalse(control.abierto)
        control.registrar_error("HTTP_429")
        self.assertFalse(control.abierto)
        control.registrar_error("HTTP_429")
        self.assertTrue(control.abierto)
        with self.assertRaisesRegex(ErrorAuditoriaIA, "CIRCUITO_ABIERTO"):
            inferir_nvidia(self.contexto, self.mapa, control=control)

    def test_401_abre_circuito_sin_filtrar_clave(self):
        control = ControlInferenciaIA()
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "clave-de-prueba"}), \
             patch("src.proveedor_nvidia.urlopen", side_effect=HTTPError(
                 "https://example.invalid", 401, "no", {}, None)):
            with self.assertRaisesRegex(ErrorAuditoriaIA, "HTTP_401"):
                inferir_nvidia(self.contexto, self.mapa, control=control, intentos=1)
        self.assertTrue(control.abierto)

    def test_sombra_apagada_no_llama_ia_y_sombra_encendida_no_cambia_fase(self):
        base = {"HISTORIAL_ACTUACIONES": [{
            "fecha": "08/07/2026",
            "detalle": "PUBLICACION Y FECHA PARA REMATE (AUTO INTERLOCUTORIO)",
        }]}
        apagado = BotJudicial("https://example.invalid", inferencia_ia={
            "sombra_en_lote": False,
        })
        con_sombra = BotJudicial("https://example.invalid", inferencia_ia={
            "sombra_en_lote": True,
        })
        with patch("src.inferencia_dual.comparar", side_effect=AssertionError("llamada")):
            oficial = apagado._aplicar_inferencia_consolidada(
                dict(base), causa="07333-2019-00278", alcance="causa"
            )
        with patch("src.inferencia_dual.comparar", side_effect=ErrorAuditoriaIA("HTTP_429")):
            fallida = con_sombra._aplicar_inferencia_consolidada(
                dict(base), causa="07333-2019-00278", alcance="causa"
            )
        self.assertEqual(oficial, fallida)

    def test_comparacion_seudonima_y_huella_estable(self):
        motor = {
            "ULTIMA_ETAPA": "1 PRESENTACION Y CALIFICACION",
            "ULTIMA_FASE": "1.3 CALIFICACION",
            "ETAPA_ACTUAL": "2 CITACION", "FASE_ACTUAL": "2.1 CITACION",
        }
        actuaciones = self.datos["HISTORIAL_ACTUACIONES"]
        def inferencia_falsa(_contexto, mapa, **_opciones):
            return validar_inferencia(self.decision, mapa), {"total_tokens": 25}

        with patch("src.inferencia_dual.inferir_nvidia", side_effect=inferencia_falsa):
            registro, _ = comparar("07333-2019-00278", self.datos, actuaciones, motor)
        self.assertEqual(registro["huella_contexto"], huella_motor(
            "07333-2019-00278", self.datos, actuaciones, motor
        ))
        self.assertTrue(registro["coincide_actual"])
        self.assertTrue(registro["coincide_ultimo"])
        self.assertEqual(registro["tokens"], 25)
        self.assertNotIn("JUAN PEREZ", json.dumps(registro))
        with patch("src.inferencia_dual.inferir_nvidia", side_effect=inferencia_falsa):
            persistido, _ = comparar("07333-2019-00278", self.datos, [{
                **actuaciones[0], "actuacion_id": "ID_PERSISTIDO",
            }], motor)
        self.assertEqual(persistido["evidencias"], ["ID_PERSISTIDO"])
        self.assertNotEqual(persistido["huella_contexto"], registro["huella_contexto"])

    def test_reporte_usa_etiquetas_y_cuenta_falsos_avances(self):
        self.assertEqual(seudonimo("CAUSA-1", b"x" * 20),
                         seudonimo("CAUSA-1", b"x" * 20))
        filas = [{
            "id_seudonimo": "p1", "motor_eta_actual": 11,
            "motor_fas_actual": 80, "motor_eta_ultimo": 10,
            "motor_fas_ultimo": 79, "ia_eta_actual": 12,
            "ia_fas_actual": 82, "ia_eta_ultimo": 11,
            "ia_fas_ultimo": 80, "error": None,
            "latencia_ms": 200, "tokens": 30,
        }]
        etiquetas = {"p1": {
            "eta_id_actual_correcta": "11", "fas_id_actual_correcta": "80",
            "eta_id_ultimo_correcta": "10", "fas_id_ultimo_correcta": "79",
        }}
        m = evaluar(filas, etiquetas)
        self.assertEqual(m["motor"]["par_actual_correcto"], 1)
        self.assertEqual(m["ia"]["par_actual_correcto"], 0)
        self.assertEqual(m["ia"]["falsos_avances_actual"], 1)
        self.assertIn("Causas etiquetadas y válidas: **1**", redactar_reporte(m))

    def test_jerarquia_ia_y_respaldo_por_confianza_o_error(self):
        original = {
            "ULTIMA ETAPA": "1 PRESENTACION Y CALIFICACION",
            "ULTIMA FASE": "1.3 CALIFICACION",
            "ETAPA ACTUAL": "2 CITACION", "FASE ACTUAL": "2.1 CITACION",
            "FECHA FIN ULTIMA FASE": "01/01/2025",
            "FECHA INICIO FASE ACTUAL": "02/01/2025",
            "FECHA INICIAL FASE ACTUAL": "02/01/2025",
        }
        propuesta = {"estado": "OK", "confianza": 0.91,
                     "requiere_revision_humana": False,
                     "ultimo_hito": {"eta_id": 11, "fas_id": 80},
                     "estado_actual": {"eta_id": 12, "fas_id": 82}}
        config = {"jerarquia": "ia_primero", "umbral_confianza": 0.75}
        elegido = aplicar_jerarquia(dict(original), {"error": None}, propuesta, config)
        self.assertEqual(elegido["FUENTE_INFERENCIA"], "IA")
        self.assertEqual(elegido["FASE ACTUAL"], "3.1 CONTESTACION")
        self.assertEqual(elegido["FECHA INICIO FASE ACTUAL"], "02/01/2025")
        self.assertEqual(elegido["FECHA INICIAL FASE ACTUAL"], "02/01/2025")
        self.assertEqual(elegido["FECHA FIN ULTIMA FASE"], "01/01/2025")
        self.assertEqual(elegido["FUENTE_FECHAS"], "MOTOR")
        self.assertEqual(elegido["MOTIVO_FUENTE"], "IA_CON_FECHAS_MOTOR")
        self.assertEqual(elegido["fas_id FASE ACTUAL"], 82)
        inconsistente = aplicar_jerarquia(
            dict(original), {"error": None},
            {**propuesta, "estado_actual": propuesta["ultimo_hito"]}, config,
        )
        self.assertEqual(inconsistente["FUENTE_INFERENCIA"], "MOTOR_RESPALDO")
        self.assertEqual(inconsistente["MOTIVO_FUENTE"], "IA_TRANSICION_INCONSISTENTE")
        baja = aplicar_jerarquia(dict(original), {"error": None},
                                 {**propuesta, "confianza": 0.4}, config)
        self.assertEqual(baja["FUENTE_INFERENCIA"], "MOTOR_RESPALDO")
        self.assertEqual(baja["FASE ACTUAL"], original["FASE ACTUAL"])
        agotada = aplicar_jerarquia(dict(original), {"error": "HTTP_402"}, None, config)
        self.assertEqual(agotada["MOTIVO_FUENTE"], "IA_HTTP_402")
        motor = aplicar_jerarquia(dict(original), None, None, {"jerarquia": "motor"})
        self.assertEqual(motor["FASE ACTUAL"], original["FASE ACTUAL"])
        self.assertEqual(motor["FUENTE_INFERENCIA"], "MOTOR")


if __name__ == "__main__":
    unittest.main()
