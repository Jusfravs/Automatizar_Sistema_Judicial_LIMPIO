"""Contratos públicos de selección de causas, sin E/S ni navegador."""

import unittest

from main import dividir_en_bloques, seleccionar_casos
from src import seleccion_ejecucion


class SeleccionEjecucionTests(unittest.TestCase):
    def setUp(self):
        self.casos = [
            "07331-2024-00277",
            "07331-2025-00296",
            "07331-2026-00445",
            "07333-2015-02213",
        ]

    def test_main_conserva_las_importaciones_publicas(self):
        self.assertIs(seleccionar_casos, seleccion_ejecucion.seleccionar_casos)
        self.assertIs(dividir_en_bloques, seleccion_ejecucion.dividir_en_bloques)

    def test_sin_argumentos_conserva_orden_y_no_modifica_la_entrada(self):
        original = list(self.casos)
        seleccion = seleccionar_casos(self.casos, [])
        self.assertEqual(seleccion, original)
        self.assertIsNot(seleccion, self.casos)
        self.assertEqual(self.casos, original)
        self.assertEqual(seleccionar_casos(self.casos, None), original)

    def test_continuacion_posicional_empieza_en_la_coincidencia(self):
        self.assertEqual(
            seleccionar_casos(self.casos, ["07331202600445"]),
            self.casos[2:],
        )
        self.assertEqual(
            seleccionar_casos(self.casos, ["07331-2026-00445"]),
            self.casos[2:],
        )

    def test_continuacion_posicional_no_encontrada_conserva_todos(self):
        self.assertEqual(
            seleccionar_casos(self.casos, ["07331-2020-00001"]),
            self.casos,
        )
        with self.assertRaisesRegex(ValueError, "ARGUMENTOS_INVALIDOS"):
            seleccionar_casos(self.casos, [self.casos[0], self.casos[1]])

    def test_solo_equivale_con_y_sin_guiones(self):
        for objetivo in ("07331-2025-00296", "07331202500296"):
            with self.subTest(objetivo=objetivo):
                self.assertEqual(
                    seleccionar_casos(self.casos, ["--solo", objetivo]),
                    [self.casos[1]],
                )

    def test_solo_rechaza_causa_ausente_o_argumentos_adicionales(self):
        for argumentos in (
            ["--solo"],
            ["--solo", ""],
            ["--solo", self.casos[0], self.casos[1]],
        ):
            with self.subTest(argumentos=argumentos):
                with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
                    seleccionar_casos(self.casos, argumentos)
        with self.assertRaisesRegex(ValueError, "CAUSA_SOLO_NO_ENCONTRADA"):
            seleccionar_casos(self.casos, ["--solo", "07331-2020-00001"])

    def test_lote_respeta_ambos_limites_y_recorta_sin_modificar(self):
        casos = [f"07331-2026-{numero:05d}" for numero in range(101)]
        self.assertEqual(seleccionar_casos(casos, ["--lote", "2"]), casos[:2])
        self.assertEqual(seleccionar_casos(casos, ["--lote", "100"]), casos[:100])
        self.assertEqual(len(casos), 101)

    def test_lote_rechaza_cantidad_fuera_de_rango_y_no_numerica(self):
        for cantidad in ("1", "101"):
            with self.subTest(cantidad=cantidad):
                with self.assertRaisesRegex(ValueError, "LOTE_FUERA_DE_RANGO"):
                    seleccionar_casos(self.casos, ["--lote", cantidad])
        for argumentos in (["--lote"], ["--lote", "dos"]):
            with self.subTest(argumentos=argumentos):
                with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
                    seleccionar_casos(self.casos, argumentos)

    def test_excluir_recorta_despues_de_excluir_y_acepta_id_normalizado(self):
        self.assertEqual(
            seleccionar_casos(
                self.casos, ["--lote", "2", "--excluir", "07331202500296"]
            ),
            [self.casos[0], self.casos[2]],
        )
        self.assertEqual(
            seleccionar_casos(
                self.casos, ["--lote", "2", "--excluir", self.casos[3]]
            ),
            self.casos[:2],
        )

    def test_excluir_repetido_y_varias_exclusiones_no_reducen_el_cupo(self):
        self.assertEqual(
            seleccionar_casos(
                self.casos,
                [
                    "--lote", "2",
                    "--excluir", self.casos[0],
                    "--excluir", "07331202400277",
                    "--excluir", self.casos[2],
                ],
            ),
            [self.casos[1], self.casos[3]],
        )

    def test_excluir_rechaza_inexistente_y_uso_fuera_de_lote(self):
        with self.assertRaisesRegex(ValueError, "CAUSA_EXCLUIDA_NO_ENCONTRADA"):
            seleccionar_casos(
                self.casos, ["--lote", "2", "--excluir", "07331-2020-00001"]
            )
        for argumentos in (
            ["--excluir", self.casos[0]],
            ["--lote", "2", "--excluir"],
            ["--lote", "2", "--excluir", ""],
        ):
            with self.subTest(argumentos=argumentos):
                with self.assertRaises(ValueError):
                    seleccionar_casos(self.casos, argumentos)

    def test_pendientes_preserva_las_causas_recibidas(self):
        casos = [self.casos[0], self.casos[0], self.casos[1]]
        self.assertEqual(seleccionar_casos(casos, ["--pendientes"]), casos)
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--pendientes", "extra"])

    def test_reprocesar_filtro_deduplica_por_id_y_conserva_primera_forma(self):
        casos = [
            self.casos[0],
            "07331202400277",
            self.casos[1],
            self.casos[0],
            self.casos[2],
        ]
        self.assertEqual(
            seleccionar_casos(casos, ["--reprocesar-filtro"]),
            [self.casos[0], self.casos[1], self.casos[2]],
        )
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--reprocesar-filtro", "extra"])

    def test_dividir_en_bloques_respetando_sesiones_de_diez(self):
        casos = [f"CAUSA-{numero:03d}" for numero in range(21)]
        self.assertEqual(dividir_en_bloques([]), [])
        self.assertEqual(dividir_en_bloques(casos[:10]), [casos[:10]])
        self.assertEqual(
            dividir_en_bloques(casos),
            [casos[:10], casos[10:20], casos[20:]],
        )
        self.assertEqual(dividir_en_bloques(casos[:5], 2), [casos[:2], casos[2:4], casos[4:5]])

    def test_dividir_en_bloques_rechaza_tamano_invalido(self):
        for tamano in (0, -1):
            with self.subTest(tamano=tamano):
                with self.assertRaisesRegex(ValueError, "TAMANO_BLOQUE_INVALIDO"):
                    dividir_en_bloques(self.casos, tamano)


if __name__ == "__main__":
    unittest.main()
