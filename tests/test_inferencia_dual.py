"""Inferencia NVIDIA independiente: privacidad, catálogo y fallos controlados."""

import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from src.proveedor_nvidia import (
    ControlInferenciaIA, ErrorAuditoriaIA, anonimizar_texto,
    construir_contexto_inferencia, inferir_nvidia, validar_inferencia,
)


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
            "estado_actual": {"eta_id": 11, "fas_id": 80},
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
        for cambio in (
            {"evidencias": ["A999"]},
            {"estado_actual": {"eta_id": 12, "fas_id": 80}},
            {"confianza": 1.1},
            {"evidencias": []},
        ):
            with self.subTest(cambio=cambio), self.assertRaises(ErrorAuditoriaIA):
                validar_inferencia({**self.decision, **cambio}, self.mapa)
        insuficiente = {**self.decision, "ultimo_hito": None,
                        "estado_actual": "INSUFICIENTE", "evidencias": [],
                        "requiere_revision_humana": True}
        self.assertEqual(validar_inferencia(insuficiente, self.mapa)["estado"], "INSUFICIENTE")

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


if __name__ == "__main__":
    unittest.main()
