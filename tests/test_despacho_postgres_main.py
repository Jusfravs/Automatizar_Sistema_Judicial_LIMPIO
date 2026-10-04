"""Contratos de despacho de la CLI sin navegador ni base de datos real."""

import unittest
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import main


class DespachoMainTests(unittest.TestCase):
    def _repo(self, *, motor=None, concurrencia=None):
        config = {
            "rutas": {
                "archivo_db": "estado-del-perfil.sqlite",
                "archivo_casos_fallidos": "fallidos-del-perfil.txt",
            },
            "concurrencia": concurrencia or {},
        }
        if motor is not None:
            config["base_de_datos"] = {"motor": motor}
        return SimpleNamespace(config=config, filtros={"inicio_desde_juicio": "ANTERIOR"})

    def test_postgres_entrega_perfil_ruta_y_workers_al_despacho(self):
        repo = self._repo(
            motor="postgres",
            concurrencia={"habilitada": True, "trabajadores": 2},
        )
        resultado = object()
        with patch.object(main, "GestorCasos", return_value=repo) as crear_repo, patch.object(
            main, "_ejecutar_lote_postgres", return_value=resultado
        ) as ejecutar_pg, patch.object(main, "GestorCola") as crear_cola:
            devuelto = main.main(["--config", "perfil.json", "--lote", "12", "--workers", "1"])

        self.assertIs(devuelto, resultado)
        crear_repo.assert_called_once_with("perfil.json")
        ejecutar_pg.assert_called_once_with(
            repo, ["--lote", "12"], "perfil.json", "fallidos-del-perfil.txt", 1
        )
        crear_cola.assert_not_called()

    def test_sqlite_es_motor_por_defecto_y_usa_su_cola(self):
        repo = self._repo()
        resultado = object()
        with patch.object(main, "GestorCasos", return_value=repo), patch.object(
            main, "GestorCola"
        ) as crear_cola, patch.object(
            main, "_ejecutar_lote", return_value=resultado
        ) as ejecutar_sqlite, patch.object(main, "_ejecutar_lote_postgres") as ejecutar_pg:
            devuelto = main.main(["--config", "perfil.json", "--pendientes"])

        self.assertIs(devuelto, resultado)
        crear_cola.assert_called_once_with(ruta_db="estado-del-perfil.sqlite")
        crear_cola.return_value.bloquear_ejecucion.assert_called_once_with()
        ejecutar_sqlite.assert_called_once_with(
            repo, crear_cola.return_value, ["--pendientes"], "fallidos-del-perfil.txt"
        )
        ejecutar_pg.assert_not_called()

    def test_solo_rechaza_dos_workers_antes_de_abrir_cola(self):
        repo = self._repo(motor="postgres")
        with patch.object(main, "GestorCasos", return_value=repo), patch.object(
            main, "_ejecutar_lote_postgres"
        ) as ejecutar_pg, patch.object(main, "GestorCola") as crear_cola:
            with self.assertRaisesRegex(ValueError, "MODO_SOLO_REQUIERE_UN_TRABAJADOR"):
                main.main(["--solo", "01-01", "--workers", "2"])

        ejecutar_pg.assert_not_called()
        crear_cola.assert_not_called()

    def test_sqlite_rechaza_concurrencia_antes_de_abrir_cola(self):
        repo = self._repo()
        with patch.object(main, "GestorCasos", return_value=repo), patch.object(
            main, "GestorCola"
        ) as crear_cola:
            with self.assertRaisesRegex(RuntimeError, "POSTGRES_REQUERIDO_PARA_CONCURRENCIA"):
                main.main(["--lote", "2", "--workers", "2"])

        crear_cola.assert_not_called()


class PreparacionLotePostgresTests(unittest.TestCase):
    def _repo(self, causas, eventos):
        repo = SimpleNamespace(
            filtros={"inicio_desde_juicio": "ANTERIOR"},
            config={"base_de_datos": {"motor": "postgres", "base": "aislada"}},
        )

        def obtener():
            eventos.append(("candidatos", repo.filtros["inicio_desde_juicio"]))
            return list(causas)

        repo.obtener_casos_pendientes = obtener
        return repo

    def test_continuacion_respeta_orden_exclusion_limite_y_resultado(self):
        eventos = []
        repo = self._repo(
            ["01-01", "02-02", "0202", "03-03", "04-04", "05-05"], eventos
        )
        resultado = {
            "ejecucion_id": "falsa",
            "estado": "COMPLETADA",
            "estadisticas": {"PROCESADO": 2},
        }

        def crear_pg(config):
            eventos.append(("crear_pg", config))
            return SimpleNamespace(listar_causas_procesadas=listar_procesadas)

        def listar_procesadas():
            eventos.append(("procesadas",))
            return ["0101"]

        class CoordinadorFalso:
            def __init__(self, gestor, perfil, *, trabajadores):
                eventos.append(("coordinador", gestor, perfil, trabajadores))

            def ejecutar(self, causas, ruta_fallidos):
                eventos.append(("ejecutar", list(causas), ruta_fallidos))
                return resultado

        with patch(
            "src.repositorio_postgres.RepositorioColaPostgres.desde_config",
            side_effect=crear_pg,
        ), patch(
            "src.coordinador_concurrente.CoordinadorConcurrente",
            CoordinadorFalso,
        ):
            devuelto = main._ejecutar_lote_postgres(
                repo,
                ["--lote", "2", "--excluir", "04-04", "--omitir-procesados"],
                "perfil.json",
                "fallidos.txt",
                2,
            )

        self.assertIs(devuelto, resultado)
        self.assertEqual(
            eventos,
            [
                ("candidatos", None),
                ("crear_pg", repo.config["base_de_datos"]),
                ("procesadas",),
                ("coordinador", repo, "perfil.json", 2),
                ("ejecutar", ["02-02", "03-03"], "fallidos.txt"),
            ],
        )

    def test_opcion_omitir_duplicada_no_consulta_postgres(self):
        eventos = []
        repo = self._repo(["01-01"], eventos)
        with patch(
            "src.repositorio_postgres.RepositorioColaPostgres.desde_config"
        ) as crear_pg, patch(
            "src.coordinador_concurrente.CoordinadorConcurrente"
        ) as crear_coordinador:
            with self.assertRaisesRegex(ValueError, "OPCION_OMITIR_PROCESADOS_DUPLICADA"):
                main._ejecutar_lote_postgres(
                    repo,
                    ["--pendientes", "--omitir-procesados", "--omitir-procesados"],
                    "perfil.json",
                    "fallidos.txt",
                    2,
                )

        self.assertEqual(eventos, [("candidatos", None)])
        crear_pg.assert_not_called()
        crear_coordinador.assert_not_called()

    def test_omitir_procesados_en_modo_solo_es_invalido(self):
        repo = self._repo(["01-01"], [])
        with patch(
            "src.repositorio_postgres.RepositorioColaPostgres.desde_config"
        ) as crear_pg, patch(
            "src.coordinador_concurrente.CoordinadorConcurrente"
        ) as crear_coordinador:
            with self.assertRaisesRegex(ValueError, "USO_INVALIDO: --solo"):
                main._ejecutar_lote_postgres(
                    repo,
                    ["--solo", "01-01", "--omitir-procesados"],
                    "perfil.json",
                    "fallidos.txt",
                    1,
                )

        crear_pg.assert_not_called()
        crear_coordinador.assert_not_called()

    def test_lote_vacio_limpia_fallidos_sin_crear_coordinador(self):
        repo = self._repo([], [])
        with patch.object(main, "guardar_casos_fallidos") as guardar, patch(
            "src.coordinador_concurrente.CoordinadorConcurrente"
        ) as crear_coordinador:
            devuelto = main._ejecutar_lote_postgres(
                repo, ["--pendientes"], "perfil.json", "fallidos.txt", 2
            )

        self.assertIsNone(devuelto)
        guardar.assert_called_once_with([], "fallidos.txt")
        crear_coordinador.assert_not_called()

    def test_dependencias_postgres_se_resuelven_al_ejecutar(self):
        repo = self._repo(["01-01"], [])
        resultado = {
            "ejecucion_id": "falsa",
            "estado": "COMPLETADA",
            "estadisticas": {},
        }
        eventos = []

        class RepositorioFalso:
            @classmethod
            def desde_config(cls, config):
                eventos.append(("repositorio", config))
                return cls()

            def listar_causas_procesadas(self):
                return []

        class CoordinadorFalso:
            def __init__(self, gestor, perfil, *, trabajadores):
                eventos.append(("coordinador", gestor, perfil, trabajadores))

            def ejecutar(self, causas, ruta_fallidos):
                eventos.append(("ejecutar", causas, ruta_fallidos))
                return resultado

        modulo_repo = ModuleType("src.repositorio_postgres")
        modulo_repo.RepositorioColaPostgres = RepositorioFalso
        modulo_coordinador = ModuleType("src.coordinador_concurrente")
        modulo_coordinador.CoordinadorConcurrente = CoordinadorFalso
        with patch.dict(
            sys.modules,
            {
                "src.repositorio_postgres": modulo_repo,
                "src.coordinador_concurrente": modulo_coordinador,
            },
        ):
            devuelto = main._ejecutar_lote_postgres(
                repo,
                ["--pendientes", "--omitir-procesados"],
                "perfil.json",
                "fallidos.txt",
                2,
            )

        self.assertIs(devuelto, resultado)
        self.assertEqual(
            eventos,
            [
                ("repositorio", repo.config["base_de_datos"]),
                ("coordinador", repo, "perfil.json", 2),
                ("ejecutar", ["01-01"], "fallidos.txt"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
