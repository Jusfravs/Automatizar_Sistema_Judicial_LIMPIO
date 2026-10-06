import os
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import main as main_module
from main import (
    actualizar_casos_fallidos_piloto,
    dividir_en_bloques,
    guardar_casos_fallidos,
    extraer_ruta_config,
    guardar_csv_o_fallar,
    motivo_revision_manual_por_formato,
    seleccionar_casos,
)
from src.motor_busqueda_web import BotJudicial


CAUSA = "23331202202089"


class ColeccionFalsa:
    def __init__(self, elementos=None):
        self.elementos = list(elementos or [])

    def count(self):
        return len(self.elementos)

    def nth(self, indice):
        return self.elementos[indice]


class ControlFalso:
    def __init__(self, al_click=None, visible=True, editable=True, texto="Regresar"):
        self.al_click = al_click
        self.visible = visible
        self.editable = editable
        self.texto = texto
        self.clicks = 0

    def is_visible(self):
        return self.visible

    def is_editable(self):
        return self.editable

    def is_enabled(self):
        return self.editable

    def click(self):
        self.clicks += 1
        if self.al_click:
            self.al_click()

    def get_attribute(self, nombre):
        return None

    def inner_text(self):
        return self.texto


class PaginaRetornoFalsa:
    def __init__(self, url="https://ejemplo.local/movimientos", campos=0, botones=None, directos=None):
        self.url = url
        self.campos = campos
        self.botones = list(botones or [])
        self.directos = list(directos or [])
        self.go_backs = 0
        self.esperas = 0

    def is_closed(self):
        return False

    def locator(self, selector):
        if selector.startswith("input["):
            return ColeccionFalsa([ControlFalso(texto="causa") for _ in range(self.campos)])
        if selector.startswith("button:has-text"):
            return ColeccionFalsa(self.botones)
        if selector.startswith("a[href='/busqueda-filtros']"):
            return ColeccionFalsa(self.directos)
        return ColeccionFalsa()

    def wait_for_timeout(self, milisegundos):
        self.esperas += 1

    def go_back(self):
        self.go_backs += 1
        self.url = "https://ejemplo.local/busqueda-filtros"
        self.campos = 1


class RetornoBuscadorTests(unittest.TestCase):
    def crear_bot(self, pagina=None):
        bot = BotJudicial("https://ejemplo.local")
        bot.page = pagina or PaginaRetornoFalsa()
        return bot

    @staticmethod
    def diagnostico(listo, url=None):
        return {
            "url": url or (
                "https://ejemplo.local/busqueda-filtros"
                if listo else "https://ejemplo.local/movimientos"
            ),
            "listo": listo,
        }

    def test_transicion_segunda_carpeta_esta_permitida(self):
        bot = self.crear_bot()
        bot.ultimo_estado_navegacion = "MOVIMIENTOS_LISTOS"

        bot._cambiar_estado_navegacion(
            CAUSA,
            "MOVIMIENTOS_LISTOS",
            "ABRIENDO_INFORMACION_PROCESO",
            "segunda_carpeta",
        )

        self.assertEqual(bot.ultimo_estado_navegacion, "ABRIENDO_INFORMACION_PROCESO")

    def test_detector_exige_un_unico_campo_editable(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=1
        )
        bot = self.crear_bot(pagina)
        self.assertTrue(bot._diagnosticar_buscador()["listo"])

        pagina.campos = 2
        diagnostico = bot._diagnosticar_buscador()
        self.assertFalse(diagnostico["listo"])
        self.assertEqual(diagnostico["campos_causa"], 2)

    def test_capa_de_carga_visible_impide_reutilizar_el_buscador(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=1
        )
        bot = self.crear_bot(pagina)
        bot._hay_carga_visible = lambda: True

        diagnostico = bot._diagnosticar_buscador()

        self.assertTrue(diagnostico["carga_visible"])
        self.assertFalse(diagnostico["listo"])

    def test_espera_requiere_dos_observaciones_estables(self):
        bot = self.crear_bot()
        respuestas = iter([
            self.diagnostico(False),
            self.diagnostico(True),
            self.diagnostico(True),
        ])
        bot._diagnosticar_buscador = lambda: next(respuestas)

        resultado = bot._esperar_buscador_listo(CAUSA, timeout_ms=1000)

        self.assertTrue(resultado["listo"])
        self.assertEqual(bot.page.esperas, 2)

    def test_buscador_ya_listo_no_navega(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=1
        )
        bot = self.crear_bot(pagina)

        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertEqual(pagina.go_backs, 0)
        self.assertEqual(bot._retorno_buscador_actual["clicks"], 0)
        self.assertEqual(bot._retorno_buscador_actual["estrategia"], "ya_visible")

    def test_retorno_preparatorio_no_consume_el_retorno_terminal(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=1
        )
        bot = self.crear_bot(pagina)
        bot.ultimo_numero_juicio = CAUSA
        bot.ultimo_estado_navegacion = "PREPARAR_BUSCADOR"

        self.assertTrue(bot.regresar_al_buscador())

        self.assertIsNone(bot._retorno_buscador_actual)
        self.assertIsNotNone(bot._retorno_buscador_preparacion)
        self.assertTrue(bot._retorno_buscador_preparacion["confirmado"])

        bot.ultimo_estado_navegacion = "RETORNANDO_AL_BUSCADOR"
        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertIsNotNone(bot._retorno_buscador_actual)

    def test_ruta_busqueda_espera_hasta_que_angular_monte_el_campo(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=0
        )
        bot = self.crear_bot(pagina)
        esperas = []

        def esperar(causa):
            esperas.append(causa)
            pagina.campos = 1
            return bot._diagnosticar_buscador()

        bot._esperar_buscador_listo = esperar

        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertEqual(esperas, [CAUSA])
        self.assertEqual(pagina.go_backs, 0)
        self.assertEqual(
            bot._retorno_buscador_actual["estrategia"],
            "ruta_busqueda_pendiente",
        )

    def test_ruta_busqueda_vacia_hace_una_recarga_controlada(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=0
        )
        bot = self.crear_bot(pagina)
        recargas = []

        def recargar(**kwargs):
            recargas.append(kwargs)
            pagina.campos = 1

        def esperar(causa):
            diagnostico = bot._diagnosticar_buscador()
            if not diagnostico["listo"]:
                raise RuntimeError("ANGULAR_NO_MONTADO")
            return diagnostico

        pagina.reload = recargar
        bot._esperar_buscador_listo = esperar

        self.assertTrue(bot._volver_al_buscador(CAUSA))

        self.assertEqual(len(recargas), 1)
        self.assertEqual(recargas[0]["wait_until"], "domcontentloaded")
        self.assertEqual(bot._retorno_buscador_actual["recargas"], 1)
        self.assertEqual(
            bot._retorno_buscador_actual["estrategia"],
            "ruta_busqueda_recarga",
        )

    def test_click_sin_transicion_usa_un_solo_go_back(self):
        control = ControlFalso()
        pagina = PaginaRetornoFalsa(botones=[control])
        bot = self.crear_bot(pagina)
        bot._diagnosticar_buscador = lambda: self.diagnostico(
            pagina.url.endswith("busqueda-filtros"), pagina.url
        )

        def esperar(causa):
            diagnostico = bot._diagnosticar_buscador()
            if not diagnostico["listo"]:
                raise RuntimeError("SIN_TRANSICION")
            return diagnostico

        bot._esperar_buscador_listo = esperar

        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertEqual(control.clicks, 1)
        self.assertEqual(pagina.go_backs, 1)
        self.assertEqual(bot._retorno_buscador_actual["clicks"], 1)
        self.assertEqual(bot._retorno_buscador_actual["go_back"], 1)

        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertEqual(control.clicks, 1)
        self.assertEqual(pagina.go_backs, 1)

    def _bot_sin_salida(self, pagina):
        """Bot cuyo botón Regresar y go_back no cambian de pantalla."""
        bot = self.crear_bot(pagina)
        bot.url_portal = "https://ejemplo.local/busqueda-filtros"
        pagina.go_back = lambda: setattr(pagina, "go_backs", pagina.go_backs + 1)
        bot._diagnosticar_buscador = lambda: self.diagnostico(
            pagina.url.endswith("busqueda-filtros"), pagina.url
        )

        def esperar(causa):
            diagnostico = bot._diagnosticar_buscador()
            if not diagnostico["listo"]:
                raise RuntimeError("SIN_TRANSICION")
            return diagnostico

        bot._esperar_buscador_listo = esperar
        return bot

    def test_si_regresar_y_go_back_fallan_abre_el_buscador_por_url(self):
        control = ControlFalso()
        pagina = PaginaRetornoFalsa(botones=[control])
        visitas = []

        def goto(url, **kwargs):
            visitas.append(url)
            pagina.url = url
            pagina.campos = 1

        pagina.goto = goto
        bot = self._bot_sin_salida(pagina)

        self.assertTrue(bot._volver_al_buscador(CAUSA))
        self.assertEqual(visitas, ["https://ejemplo.local/busqueda-filtros"])
        self.assertEqual(pagina.go_backs, 1)
        contexto = bot._retorno_buscador_actual
        self.assertTrue(contexto["confirmado"])
        self.assertEqual(contexto["goto"], 1)
        self.assertTrue(contexto["estrategia"].endswith("+goto_buscador"))

    def test_si_tambien_falla_la_url_conserva_retorno_buscador_error(self):
        pagina = PaginaRetornoFalsa(botones=[ControlFalso()])

        def goto(url, **kwargs):
            raise RuntimeError("SIN_RED")

        pagina.goto = goto
        bot = self._bot_sin_salida(pagina)
        bot._guardar_evidencia_retorno = lambda causa, contexto: None

        with self.assertRaisesRegex(RuntimeError, "RETORNO_BUSCADOR_ERROR"):
            bot._volver_al_buscador(CAUSA)
        self.assertEqual(bot._retorno_buscador_actual["error_goto"], "SIN_RED")

    def test_control_directo_al_buscador_tiene_prioridad(self):
        pagina = PaginaRetornoFalsa()

        def ir_buscador():
            pagina.url = "https://ejemplo.local/busqueda-filtros"
            pagina.campos = 1

        directo = ControlFalso(al_click=ir_buscador, texto="Búsqueda avanzada")
        regreso = ControlFalso()
        pagina.directos = [directo]
        pagina.botones = [regreso]
        bot = self.crear_bot(pagina)

        self.assertTrue(bot._volver_al_buscador(CAUSA))

        self.assertEqual(directo.clicks, 1)
        self.assertEqual(regreso.clicks, 0)
        self.assertEqual(pagina.go_backs, 0)
        self.assertEqual(
            bot._retorno_buscador_actual["tipo_control"], "buscador_directo"
        )

    def test_retorno_desde_causas_usa_control_directo(self):
        pagina = PaginaRetornoFalsa(url="https://ejemplo.local/causas")

        def ir_buscador():
            pagina.url = "https://ejemplo.local/busqueda-filtros"
            pagina.campos = 1

        directo = ControlFalso(al_click=ir_buscador, texto="Búsqueda avanzada")
        pagina.directos = [directo]
        bot = self.crear_bot(pagina)

        self.assertTrue(bot._volver_al_buscador(CAUSA))

        self.assertEqual(directo.clicks, 1)
        self.assertEqual(pagina.go_backs, 0)
        self.assertTrue(bot._retorno_buscador_actual["confirmado"])
        self.assertEqual(
            bot._retorno_buscador_actual["tipo_control"], "buscador_directo"
        )

    def _preparar_flujo_falso(self, bot):
        bot._preparar_busqueda = lambda causa: None
        bot._cambiar_estado_navegacion = (
            lambda causa, anterior, siguiente, accion, **extra:
            setattr(bot, "ultimo_estado_navegacion", siguiente)
        )
        bot._esperar_busqueda_habilitada = lambda causa: None
        bot._activar_captcha_con_click_inicial = lambda causa, intento: None
        bot._resolver_o_esperar_captcha = lambda causa, intento: None
        bot._esperar_despues_captcha = lambda causa: None
        bot._enviar_busqueda_una_vez = lambda causa, intento: None
        bot._esperar_resultados = lambda causa: {"resultado": True}
        bot._abrir_movimientos_causa = lambda causa, resultado: None

    def test_una_de_dos_carpetas_es_error_navegacion_aunque_regrese(self):
        pagina = PaginaRetornoFalsa(
            url="https://ejemplo.local/busqueda-filtros", campos=1
        )
        bot = self.crear_bot(pagina)
        self._preparar_flujo_falso(bot)
        carpeta = {"estado": "COMPLETA", "datos": {"HISTORIAL_ACTUACIONES": []}}

        def procesar(causa):
            bot._descriptores_actuales = [{"clave_carpeta": "1"}, {"clave_carpeta": "2"}]
            bot._resultados_carpeta_actuales = [carpeta]
            raise RuntimeError("FALLO_SEGUNDA_CARPETA")

        bot._procesar_todas_las_carpetas = procesar

        resultado = bot.procesar_flujo_judicatura(CAUSA)

        self.assertEqual(resultado["estado"], "ERROR_NAVEGACION")
        self.assertEqual(resultado["estado_extraccion"], "COMPLETADO")
        self.assertTrue(resultado["requiere_reintento"])
        self.assertTrue(resultado["regreso_confirmado"])
        self.assertEqual(resultado["carpetas_descubiertas"], 2)

    def test_uno_de_uno_con_confirmacion_tardia_conserva_completado(self):
        pagina = PaginaRetornoFalsa()
        bot = self.crear_bot(pagina)
        self._preparar_flujo_falso(bot)
        carpeta = {
            "estado": "COMPLETA",
            "datos": {"HISTORIAL_ACTUACIONES": []},
        }

        def procesar(causa):
            bot._descriptores_actuales = [{"clave_carpeta": "1"}]
            bot._resultados_carpeta_actuales = [carpeta]
            return bot._consolidar_resultados_carpetas(causa, [carpeta])

        def volver(causa):
            bot._retorno_buscador_actual = {
                "iniciado": True,
                "finalizado": True,
                "confirmado": False,
                "clicks": 1,
                "go_back": 0,
            }
            pagina.url = "https://ejemplo.local/busqueda-filtros"
            pagina.campos = 1
            raise RuntimeError("RETORNO_BUSCADOR_TIMEOUT")

        bot._procesar_todas_las_carpetas = procesar
        bot._volver_al_buscador = volver

        resultado = bot.procesar_flujo_judicatura(CAUSA)

        self.assertEqual(resultado["estado"], "COMPLETADO")
        self.assertEqual(resultado["estado_extraccion"], "COMPLETADO")
        self.assertTrue(resultado["regreso_confirmado"])
        self.assertFalse(resultado["requiere_reintento"])
        self.assertTrue(resultado["retorno_buscador"]["confirmacion_tardia"])

    def test_modo_solo_no_puede_ampliarse_al_lote(self):
        casos = ["23331-2022-02089", "23331-2022-03524"]

        self.assertEqual(
            seleccionar_casos(casos, ["--solo", "23331202203524"]),
            ["23331-2022-03524"],
        )
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--solo"])
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--solo", casos[0], casos[1]])

    def test_config_se_extrae_sin_interferir_con_el_modo(self):
        ruta, argumentos = extraer_ruta_config([
            "--config", "config_santo_domingo.json", "--lote", "5"
        ])

        self.assertEqual(ruta, "config_santo_domingo.json")
        self.assertEqual(argumentos, ["--lote", "5"])

    def test_lote_limitado_se_restringe_entre_dos_y_cien(self):
        casos = [
            "23331-2022-02089",
            "23331-2022-03524",
            "23331-2022-03525",
            "23331-2022-03526",
            "23331-2022-03527",
            "23331-2022-03528",
            "23331-2022-03529",
            "23331-2022-03530",
            "23331-2022-03531",
            "23331-2022-03532",
            "23331-2022-03533",
        ]

        self.assertEqual(seleccionar_casos(casos, ["--lote", "3"]), casos[:3])
        self.assertEqual(seleccionar_casos(casos, ["--lote", "10"]), casos[:10])
        self.assertEqual(seleccionar_casos(casos, ["--lote", "50"]), casos)
        self.assertEqual(
            seleccionar_casos(
                ["A", "B", "B", "C", "D"],
                ["--lote", "2", "--excluir", "B"],
            ),
            ["A", "C"],
        )
        with self.assertRaisesRegex(ValueError, "CAUSA_EXCLUIDA_NO_ENCONTRADA"):
            seleccionar_casos(["A", "B"], ["--lote", "2", "--excluir", "Z"])
        with self.assertRaisesRegex(ValueError, "LOTE_FUERA_DE_RANGO"):
            seleccionar_casos(casos, ["--lote", "1"])
        with self.assertRaisesRegex(ValueError, "LOTE_FUERA_DE_RANGO"):
            seleccionar_casos(casos, ["--lote", "101"])
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--lote", "tres"])

    def test_lote_largo_se_divide_en_bloques_de_diez(self):
        casos = [f"CAUSA-{indice:03d}" for indice in range(1, 26)]

        self.assertEqual(
            dividir_en_bloques(casos),
            [casos[:10], casos[10:20], casos[20:]],
        )

    def test_formato_de_causa_invalido_se_dirige_a_revision_manual(self):
        self.assertIsNone(motivo_revision_manual_por_formato("17230-2015-1663"))
        self.assertIsNone(motivo_revision_manual_por_formato("17233-2025-09166"))
        self.assertEqual(
            motivo_revision_manual_por_formato("17233-201-8029"),
            "FORMATO_CAUSA_INVALIDO",
        )

    def test_lote_largo_cierra_y_persiste_cada_bloque(self):
        class RepoFalso:
            instancias = []

            def __init__(self, _ruta_config):
                self.config = {
                    "navegacion": {"url_portal": "https://ejemplo.local"},
                    "sistema": {"intervalo_autoguardado": 100},
                    "rutas": {"archivo_casos_fallidos": ruta_fallidos},
                }
                self.filtros = {"sucursal": "PRUEBA"}
                self.exportaciones = 0
                self.actualizaciones = []
                RepoFalso.instancias.append(self)

            def obtener_casos_pendientes(self):
                return causas

            def actualizar_caso(self, causa, datos):
                self.actualizaciones.append((causa, datos))
                return True

            def guardar(self):
                return True

            def exportar_excel(self):
                self.exportaciones += 1

        class ColaFalsa:
            reservas = []

            def __init__(self, ruta_db):
                pass

            def verificar_esquema(self):
                return True

            def recuperar_huerfanos(self):
                return 0

            def bloquear_ejecucion(self):
                return nullcontext()

            def filtrar_causas_pendientes(self, candidatas):
                return list(candidatas)

            def poblar_cola(self, _causas):
                pass

            def reservar_causa(self, causa, permitir_reproceso=False):
                self.reservas.append((causa, permitir_reproceso))

            def registrar_resultado_transaccional(self, *_args, **_kwargs):
                pass

            def registrar_error_extraccion(self, *_args, **_kwargs):
                pass

            def obtener_estadisticas(self):
                return {"PROCESADO": len(causas)}

        class BotFalso:
            instancias = []

            def __init__(self, *_args, **_kwargs):
                self.inicios = 0
                self.cierres = 0
                self.causas = []
                BotFalso.instancias.append(self)

            def iniciar_navegador(self, **_kwargs):
                self.inicios += 1

            def procesar_flujo_judicatura(self, causa):
                self.causas.append(causa)
                if causa == "17230-2025-00011":
                    return {
                        "estado": "ERROR_NAVEGACION",
                        "datos": {},
                        "error": "RETORNO_BUSCADOR_ERROR",
                        # Incluso con un DOM aparentemente listo, una causa
                        # que falló al navegar exige una sesión nueva.
                        "regreso_confirmado": True,
                    }
                return {
                    "estado": "COMPLETADO",
                    "datos": {"HISTORIAL_ACTUACIONES": []},
                    "regreso_confirmado": True,
                }

            def cerrar_navegador(self):
                self.cierres += 1

        causas = [f"17230-2025-{indice:05d}" for indice in range(1, 13)]
        with tempfile.TemporaryDirectory() as temporal:
            ruta_fallidos = os.path.join(temporal, "fallidos.txt")
            with patch.object(main_module, "GestorCasos", RepoFalso), \
                 patch.object(main_module, "GestorCola", ColaFalsa), \
                 patch.object(main_module, "BotJudicial", BotFalso):
                main_module.main(["--config", "prueba.json", "--lote", "12"])

        bot = BotFalso.instancias[-1]
        repo = RepoFalso.instancias[-1]
        self.assertEqual(bot.causas, causas)
        self.assertEqual(
            ColaFalsa.reservas,
            [(causa, False) for causa in causas],
        )
        self.assertEqual(bot.inicios, 3)
        self.assertGreaterEqual(bot.cierres, 3)
        self.assertGreaterEqual(repo.exportaciones, 2)
        self.assertIn(
            (
                "17230-2025-00011",
                {
                    "COMENTARIO_ULTIMO": "REVISION MANUAL: RETORNO_BUSCADOR_ERROR",
                    "ETAPA ACTUAL": "REVISION MANUAL",
                    "FASE ACTUAL": "REVISION MANUAL",
                },
            ),
            repo.actualizaciones,
        )

    def test_excepcion_no_controlada_marca_error_y_continua_con_siguiente_causa(self):
        causas = ["17230-2025-00001", "17230-2025-00002"]

        class RepoFalso:
            def __init__(self, _ruta_config):
                self.config = {
                    "navegacion": {"url_portal": "https://ejemplo.local"},
                    "sistema": {"intervalo_autoguardado": 100},
                    "rutas": {"archivo_casos_fallidos": ruta_fallidos},
                }
                self.filtros = {"sucursal": "PRUEBA"}

            def obtener_casos_pendientes(self):
                return list(causas)

            def actualizar_caso(self, _causa, _datos):
                return True

            def guardar(self):
                return True

            def exportar_excel(self):
                pass

        class ColaFalsa:
            registros_error = []
            resultados = []
            reservas = []

            def __init__(self, ruta_db):
                pass

            def verificar_esquema(self):
                return True

            def recuperar_huerfanos(self):
                return 0

            def bloquear_ejecucion(self):
                return nullcontext()

            def filtrar_causas_pendientes(self, candidatas):
                return list(candidatas)

            def poblar_cola(self, _causas):
                pass

            def reservar_causa(self, causa, permitir_reproceso=False):
                self.reservas.append((causa, permitir_reproceso))

            def registrar_error_extraccion(self, causa, origen, detalle):
                self.registros_error.append((causa, origen, detalle))

            def registrar_resultado_transaccional(self, causa, resultado, **_kwargs):
                self.resultados.append((causa, resultado))

            def obtener_estadisticas(self):
                return {"ERROR": 1, "PROCESADO": 1}

        class BotFalso:
            causas_consultadas = []

            def __init__(self, *_args, **_kwargs):
                pass

            def iniciar_navegador(self, **_kwargs):
                pass

            def procesar_flujo_judicatura(self, causa):
                self.causas_consultadas.append(causa)
                if causa == causas[0]:
                    raise RuntimeError("FALLO_SIMULADO")
                return {
                    "estado": "COMPLETADO",
                    "datos": {"HISTORIAL_ACTUACIONES": []},
                    "regreso_confirmado": True,
                }

            def cerrar_navegador(self):
                pass

        with tempfile.TemporaryDirectory() as temporal:
            ruta_fallidos = os.path.join(temporal, "fallidos.txt")
            with patch.object(main_module, "GestorCasos", RepoFalso), \
                 patch.object(main_module, "GestorCola", ColaFalsa), \
                 patch.object(main_module, "BotJudicial", BotFalso):
                main_module.main(["--config", "prueba.json", "--lote", "2"])

            with open(ruta_fallidos, "r", encoding="utf-8") as archivo:
                fallidos = [linea.strip() for linea in archivo if linea.strip()]

        self.assertEqual(BotFalso.causas_consultadas, causas)
        self.assertEqual(
            ColaFalsa.reservas,
            [(causa, False) for causa in causas],
        )
        self.assertEqual(fallidos, [causas[0]])
        self.assertEqual(ColaFalsa.registros_error[0][0], causas[0])
        self.assertEqual(ColaFalsa.registros_error[0][1], "EXCEPCION_NO_CONTROLADA")
        self.assertEqual(ColaFalsa.resultados[0][1]["estado"], "ERROR")

    def test_modo_pendientes_conserva_el_conjunto_ya_filtrado(self):
        casos = ["CAUSA-001", "CAUSA-002"]

        self.assertEqual(seleccionar_casos(casos, ["--pendientes"]), casos)
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--pendientes", "extra"])

    def test_reprocesar_filtro_deduplica_sin_consultar_sqlite(self):
        casos = [
            "23331-2022-02089",
            "23331-2022-02089",
            "12331-2025-01009",
            "12331-2025-01009",
            "12331-2022-01273",
        ]

        self.assertEqual(
            seleccionar_casos(casos, ["--reprocesar-filtro"]),
            ["23331-2022-02089", "12331-2025-01009", "12331-2022-01273"],
        )
        with self.assertRaisesRegex(ValueError, "USO_INVALIDO"):
            seleccionar_casos(casos, ["--reprocesar-filtro", "extra"])


    def test_guardado_csv_false_es_error(self):
        class RepoFalso:
            def guardar(self):
                return False

        with self.assertRaisesRegex(RuntimeError, "PERSISTENCIA_ERROR:CSV"):
            guardar_csv_o_fallar(RepoFalso())

    def test_modo_solo_conserva_fallidos_ajenos(self):
        causa_ajena = "23331-2022-04191"
        causa_piloto = "23331-2022-03524"
        with tempfile.TemporaryDirectory() as directorio:
            ruta = os.path.join(directorio, "casos_fallidos.txt")
            guardar_casos_fallidos([causa_ajena, causa_piloto], ruta)

            resultado = actualizar_casos_fallidos_piloto(
                [causa_piloto], [], ruta
            )
            self.assertEqual(resultado, [causa_ajena])

            resultado = actualizar_casos_fallidos_piloto(
                [causa_piloto], [causa_piloto], ruta
            )
            self.assertEqual(resultado, [causa_ajena, causa_piloto])
            with open(ruta, "r", encoding="utf-8") as archivo:
                self.assertEqual(
                    [linea.strip() for linea in archivo if linea.strip()],
                    [causa_ajena, causa_piloto],
                )


if __name__ == "__main__":
    unittest.main()
