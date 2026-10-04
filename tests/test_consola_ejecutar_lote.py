import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import consola


class TestEjecutarLote(unittest.TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.cursor.fetchone.return_value = (True,)
        conexion = MagicMock()
        conexion.cursor.return_value.__enter__.return_value = self.cursor
        self.repo = MagicMock()

        @contextmanager
        def _connection():
            yield conexion

        self.repo._connection = _connection
        self.config = {"perfil": "lote-abc"}
        self.parches = [
            patch("consola.diagnostico",
                  return_value={"esquema_completo": True, "auditoria_config": True}),
            patch("consola.actualizar_casos"),
            patch("consola._repositorio", return_value=self.repo),
        ]
        for parche in self.parches:
            parche.start()
            self.addCleanup(parche.stop)

    def ejecutar(self, **opciones):
        motor = MagicMock()
        motor.main.return_value = {"estado": "COMPLETADA"}
        with patch.dict("sys.modules", {"main": motor}):
            resultado = consola.ejecutar_lote(Path("perfil"), base=Path("base.json"),
                                              config=self.config, **opciones)
        return resultado, motor.main.call_args

    def test_lote_con_continuar_y_bloqueo_del_perfil(self):
        resultado, llamada = self.ejecutar(lote=10, workers=3, continuar=True)
        self.assertEqual(resultado, {"estado": "COMPLETADA"})
        self.assertEqual(
            llamada.args[0],
            ["--config", "base.json", "--lote", "10", "--omitir-procesados", "--workers", "3"],
        )
        self.assertIs(llamada.kwargs["config_efectiva"], self.config)
        sentencias = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertEqual(sentencias, ["SELECT pg_try_advisory_lock(%s)",
                                      "SELECT pg_advisory_unlock(%s)"])

    def test_pendientes_por_defecto(self):
        _, llamada = self.ejecutar(workers=1)
        self.assertEqual(llamada.args[0],
                         ["--config", "base.json", "--pendientes", "--workers", "1"])

    def test_perfil_ocupado(self):
        self.cursor.fetchone.return_value = (False,)
        with self.assertRaisesRegex(ValueError, "PERFIL_YA_EN_EJECUCION"):
            self.ejecutar(lote=5)

    def test_solo_no_admite_continuar(self):
        with self.assertRaisesRegex(ValueError, "CONTINUAR_NO_ADMITIDO_CON_SOLO"):
            self.ejecutar(solo="X", continuar=True, workers=1)

    def test_esquema_incompleto(self):
        with patch("consola.diagnostico",
                   return_value={"esquema_completo": False, "auditoria_config": True}):
            with self.assertRaisesRegex(ValueError, "ESQUEMA_POSTGRES_INCOMPLETO"):
                self.ejecutar(lote=5)


class TestSubcomandoServicio(unittest.TestCase):
    def test_intervalo_fuera_de_rango(self):
        self.assertEqual(consola.main(["servicio", "--intervalo", "1"]), 2)

    def test_delegacion_al_servicio(self):
        with patch("src.servicio_portal.ejecutar_servicio", return_value=0) as servicio:
            self.assertEqual(consola.main(["servicio", "--config", "x.json", "--una-vez"]), 0)
        servicio.assert_called_once_with(Path("x.json"), intervalo=10, una_vez=True)


if __name__ == "__main__":
    unittest.main()
