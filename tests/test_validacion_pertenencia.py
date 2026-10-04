import unittest

from src.validacion_pertenencia import ESTADO_EXCLUIDO, validar_pertenencia_cartera


CONFIGURACION = {
    "activa": True,
    "actores_requeridos": ["FUNDACION PAREA EL DESARROLLO INTEGRAL ESPOIR"],
    "acciones_requeridas": ["COBRO DE PAGARE A LA ORDEN"],
}


class ValidacionPertenenciaTests(unittest.TestCase):
    def _datos(self, detalle):
        return {"HISTORIAL_ACTUACIONES": [{"detalle": detalle}]}

    def test_excluye_caratula_de_otro_actor_y_accion(self):
        detalle = (
            "DATOS DEL EXPEDIENTE NUMERO COMPLETO DEL JUICIO (SATJE): "
            "17233-2025-04343. ACCION: COBRO DE HONORARIOS DE ABOGADO. "
            "ESTADO DEL PROCESO: EN TRAMITE. DATOS DEL ACTOR: BETANCOURT VALENZUELA."
        )

        resultado = validar_pertenencia_cartera(
            self._datos(detalle), [], "17233-2025-04343", CONFIGURACION
        )

        self.assertEqual(resultado["estado"], ESTADO_EXCLUIDO)
        self.assertEqual(resultado["accion_detectada"], "COBRO DE HONORARIOS DE ABOGADO")

    def test_conserva_caratula_de_fundacion_y_pagare(self):
        detalle = (
            "DATOS DEL EXPEDIENTE NUMERO COMPLETO DEL JUICIO (SATJE): "
            "17233-2025-04344. ACCION: COBRO DE PAGARE A LA ORDEN. "
            "ESTADO DEL PROCESO: EN TRAMITE. DATOS DEL ACTOR: "
            "FUNDACION PAREA EL DESARROLLO INTEGRAL ESPOIR."
        )

        resultado = validar_pertenencia_cartera(
            self._datos(detalle), [], "17233-2025-04344", CONFIGURACION
        )

        self.assertIsNone(resultado)

    def test_sin_caratula_explicita_no_excluye(self):
        resultado = validar_pertenencia_cartera(
            self._datos("CALIFICACION DE DEMANDA"), [], "17233-2025-04345", CONFIGURACION
        )

        self.assertIsNone(resultado)

    def test_politica_predeterminada_protege_configuraciones_regionales_heredadas(self):
        detalle = (
            "DATOS DEL EXPEDIENTE NUMERO COMPLETO DEL JUICIO (SATJE): "
            "17233-2025-04346. ACCION: COBRO DE HONORARIOS DE ABOGADO. "
            "ESTADO DEL PROCESO: EN TRAMITE. DATOS DEL ACTOR: TERCERO AJENO."
        )

        resultado = validar_pertenencia_cartera(
            self._datos(detalle), [], "17233-2025-04346", {}
        )

        self.assertEqual(resultado["estado"], ESTADO_EXCLUIDO)


if __name__ == "__main__":
    unittest.main()
