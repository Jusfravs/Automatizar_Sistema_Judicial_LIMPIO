import unittest
from unittest.mock import patch

from src.motor_busqueda_web import BotJudicial
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from src.servicio_captcha import (
    CaptchaConfiguracionError,
    CaptchaDesafio,
    CaptchaResolucionTimeout,
    CaptchaSolucion,
)


class CampoFalso:
    def __init__(self, valor, ignorar_escritura_directa=False):
        self.valor = valor
        self.ignorar_escritura_directa = ignorar_escritura_directa
        self.llenados = []
        self.escrituras_secuenciales = []
        self.eventos = []

    def input_value(self):
        return self.valor

    def fill(self, valor):
        self.llenados.append(valor)
        if not (valor and self.ignorar_escritura_directa):
            self.valor = valor

    def press_sequentially(self, valor, delay=0):
        self.escrituras_secuenciales.append((valor, delay))
        self.valor = valor

    def dispatch_event(self, evento):
        self.eventos.append(evento)


class BotonFalso:
    def __init__(self, habilitado=True, disabled=None, clases="", etiqueta=""):
        self.habilitado = habilitado
        self.disabled = disabled
        self.clases = clases
        self.etiqueta = etiqueta
        self.clicks = 0

    def is_visible(self):
        return True

    def is_enabled(self):
        return self.habilitado

    def get_attribute(self, nombre):
        atributos = {
            "aria-disabled": "false",
            "disabled": self.disabled,
            "class": self.clases,
            "aria-label": self.etiqueta,
        }
        return atributos.get(nombre)

    def scroll_into_view_if_needed(self):
        return None

    def click(self):
        self.clicks += 1


class FilaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def is_visible(self):
        return True

    def inner_text(self):
        return self.texto


class ColeccionFalsa:
    def __init__(self, elementos):
        self.elementos = elementos

    def count(self):
        return len(self.elementos)

    def nth(self, indice):
        return self.elementos[indice]

    @property
    def first(self):
        return self.elementos[0]


class PaginaFilasFalsa:
    def __init__(self, filas):
        self.filas = filas

    def locator(self, selector):
        self.ultimo_selector = selector
        return ColeccionFalsa(self.filas)


class PaginaFilasDivFalsa(PaginaFilasFalsa):
    """Imita la lista Angular real, que no usa filas HTML ``tr``."""

    def locator(self, selector):
        self.ultimo_selector = selector
        if ".causa-individual" in selector:
            return ColeccionFalsa(self.filas)
        return ColeccionFalsa([])


class PaginaCaptchaFalsa:
    def __init__(self, renderizado):
        self.renderizado = renderizado

    def locator(self, selector):
        return ColeccionFalsa([object()] if self.renderizado else [])


class TextoFalso:
    def __init__(self, texto):
        self.texto = texto

    def inner_text(self):
        return self.texto


class EnlaceFalso:
    def __init__(self, etiqueta, al_hacer_click=None):
        self.etiqueta = etiqueta
        self.al_hacer_click = al_hacer_click
        self.clicks = 0

    def get_attribute(self, nombre):
        return self.etiqueta if nombre == "aria-label" else None

    def scroll_into_view_if_needed(self):
        return None

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def click(self):
        self.clicks += 1
        if self.al_hacer_click:
            self.al_hacer_click()


class FilaCausaFalsa(FilaFalsa):
    def __init__(self, numero_proceso, enlace):
        super().__init__(numero_proceso)
        self.numero_proceso = numero_proceso
        self.enlace = enlace

    def locator(self, selector):
        if selector == ".numero-proceso":
            return ColeccionFalsa([TextoFalso(self.numero_proceso)])
        if "movimientos" in selector:
            return ColeccionFalsa([self.enlace])
        return ColeccionFalsa([])


class PaginaAperturaCausaFalsa:
    def __init__(self):
        self.url = "https://ejemplo.local/causas"
        self.detalle = EnlaceFalso("Ver detalle del proceso judicial")

    def locator(self, selector):
        if "detalle del proceso judicial" in selector:
            return ColeccionFalsa([self.detalle])
        raise AssertionError(f"Selector global inesperado: {selector}")

    def wait_for_url(self, patron, timeout):
        return None


class PaginaEsperaFalsa:
    url = "https://ejemplo.local/busqueda-filtros"

    def __init__(self):
        self.esperas = []

    def is_closed(self):
        return False

    def wait_for_timeout(self, milisegundos):
        self.esperas.append(milisegundos)


class PaginaMensajeFalsa:
    url = "https://ejemplo.local/busqueda-filtros"

    def __init__(self, texto):
        self.texto = texto

    def is_closed(self):
        return False

    def inner_text(self, selector):
        if selector != "body":
            raise AssertionError(f"Selector inesperado: {selector}")
        return self.texto


class PaginaCargaGlobalPendienteFalsa:
    url = "https://ejemplo.local/actuaciones"

    def wait_for_url(self, patron, timeout):
        raise AssertionError("El flujo no debe depender del evento global load")


class PaginaActuacionesApiFalsa:
    url = "https://ejemplo.local/actuaciones"

    def __init__(self):
        self.esperas = []

    def is_closed(self):
        return False

    def inner_text(self, selector):
        raise AssertionError("Con API completa no debe esperar el render del DOM")

    def wait_for_timeout(self, milisegundos):
        self.esperas.append(milisegundos)


class NavegacionEsatjeTests(unittest.TestCase):
    def crear_bot(self, **navegacion):
        return BotJudicial("https://ejemplo.local", navegacion)

    def test_detecta_montaje_del_captcha(self):
        bot = self.crear_bot()
        bot.page = PaginaCaptchaFalsa(False)
        self.assertFalse(bot._captcha_renderizado())
        bot.page = PaginaCaptchaFalsa(True)
        self.assertTrue(bot._captcha_renderizado())

    def test_canoniza_causa_con_guiones(self):
        self.assertEqual(
            BotJudicial._causa_canonica("23331-2022-02089"),
            "23331202202089",
        )

    def test_formatea_causa_para_la_mascara_del_portal(self):
        self.assertEqual(
            BotJudicial._causa_para_formulario("23331202202089"),
            "23331-2022-02089",
        )
        self.assertEqual(
            BotJudicial._causa_para_formulario("23331-2022-02089"),
            "23331-2022-02089",
        )

    def test_formatea_causa_de_trece_digitos_para_la_mascara(self):
        self.assertEqual(
            BotJudicial._causa_para_formulario("1233120140845"),
            "12331-2014-0845",
        )
        self.assertEqual(
            BotJudicial._causa_para_formulario("12331-2014-0845"),
            "12331-2014-0845",
        )

    def test_escribe_causa_directamente_sin_tecleo_lento(self):
        bot = self.crear_bot()
        campo = CampoFalso("")

        estrategia = bot._escribir_causa_en_campo(campo, "23331-2022-02089")

        self.assertEqual(estrategia, "fill")
        self.assertEqual(campo.input_value(), "23331-2022-02089")
        self.assertEqual(campo.escrituras_secuenciales, [])
        self.assertEqual(campo.eventos, ["input", "change"])

    def test_escritura_directa_recurre_a_respaldo_si_la_mascara_la_rechaza(self):
        bot = self.crear_bot()
        campo = CampoFalso("", ignorar_escritura_directa=True)

        estrategia = bot._escribir_causa_en_campo(campo, "23331-2022-02089")

        self.assertEqual(estrategia, "secuencial_respaldo")
        self.assertEqual(campo.input_value(), "23331-2022-02089")
        self.assertEqual(
            campo.escrituras_secuenciales,
            [("23331-2022-02089", 0)],
        )

    def test_boton_con_disabled_html_no_se_considera_habilitado(self):
        self.assertFalse(BotJudicial._boton_habilitado(BotonFalso(disabled="true")))
        self.assertFalse(
            BotJudicial._boton_habilitado(
                BotonFalso(clases="mat-mdc-button-disabled")
            )
        )
        self.assertTrue(BotJudicial._boton_habilitado(BotonFalso()))

    def test_mezcla_api_dom_persiste_la_decision_canonica(self):
        bot = self.crear_bot()
        llamadas_dom = []
        bot._extraer_actuaciones_api = lambda paquetes: [
            {
                "fecha": "10/02/2025",
                "detalle": "CALIFICACION DE SOLICITUD Y/O DEMANDA",
            },
            {
                "fecha": "29/05/2025",
                "detalle": "CITACION: NO REALIZADA - CAMBIO DE DIRECCION",
            },
        ]
        bot.extractor.procesar_html_string = lambda contenido, registrar_decision=True: (
            llamadas_dom.append(registrar_decision) or {
                "HISTORIAL_ACTUACIONES": [{
                    "fecha": "16/07/2026",
                    "detalle": (
                        "EL ART. 56 TRATA DE CITACION POR LA PRENSA. PREVIO A "
                        "PROVEER, EL ACTOR DEBE AGOTAR REGISTROS PUBLICOS."
                    ),
                }],
            }
        )

        datos = bot._ejecutar_extraccion_detalles(
            "07333-2025-00183", paquetes_api=[{}], contenido_html="<html />"
        )

        self.assertEqual(llamadas_dom, [False])
        self.assertEqual(datos["ORIGEN_DATA"], "API+DOM")
        self.assertEqual(datos["ULTIMA FASE"], "1.3 CALIFICACION")
        self.assertEqual(datos["FECHA FIN ULTIMA FASE"], "10/02/2025")
        self.assertEqual(datos["FASE ACTUAL"], "2.1 CITACION (PERSONA/BOLETA)")

    def test_espera_tres_segundos_y_revalida_antes_de_buscar(self):
        bot = self.crear_bot()
        bot.page = PaginaEsperaFalsa()
        bot.captcha_config["espera_post_solucion_ms"] = 3000
        bot._input_causa_unico = lambda: CampoFalso("23331-2022-02089")
        bot._boton_buscar_unico = lambda: BotonFalso()
        bot._captcha_visible = lambda: False

        bot._esperar_despues_captcha("23331202202089")

        self.assertEqual(bot.page.esperas, [3000])

    def test_espera_post_captcha_por_defecto_es_corta(self):
        bot = self.crear_bot()

        self.assertEqual(bot.captcha_config["espera_post_solucion_ms"], 500)

    def test_espera_post_api_acepta_widget_montado_si_buscar_sigue_habilitado(self):
        bot = self.crear_bot()
        bot.page = PaginaEsperaFalsa()
        boton = BotonFalso()
        bot.captcha_config["espera_post_solucion_ms"] = 0
        bot._input_causa_unico = lambda: CampoFalso("23331-2022-02089")
        bot._boton_buscar_unico = lambda: boton
        bot._captcha_visible = lambda: True
        bot._captcha_solucion_actual = CaptchaSolucion(
            "token-secreto", 77, "2captcha", 5000, 0.1
        )

        resultado = bot._esperar_despues_captcha("23331202202089")

        self.assertIs(resultado, boton)

    def test_espera_post_manual_con_captcha_visible_se_detiene(self):
        bot = self.crear_bot()
        bot.page = PaginaEsperaFalsa()
        bot.captcha_config["espera_post_solucion_ms"] = 0
        bot._input_causa_unico = lambda: CampoFalso("23331-2022-02089")
        bot._boton_buscar_unico = lambda: BotonFalso()
        bot._captcha_visible = lambda: True
        bot._captcha_solucion_actual = None

        with self.assertRaisesRegex(
            RuntimeError, "CAPTCHA_PERDIDO_DURANTE_ESPERA_POST_SOLUCION"
        ):
            bot._esperar_despues_captcha("23331202202089")

    def test_click_inicial_transiciona_hasta_busqueda_habilitada(self):
        bot = self.crear_bot()
        bot.page = PaginaEsperaFalsa()
        campo = CampoFalso("23331-2022-02089")
        boton = BotonFalso()
        bot._input_causa_unico = lambda: campo
        bot._boton_buscar_unico = lambda: boton
        bot._captcha_renderizado = lambda: True
        bot.ultimo_estado_navegacion = "ESPERAR_FIN_CAPTCHA"

        bot._activar_captcha_con_click_inicial(
            "23331202202089", "intento:busqueda-1"
        )

        self.assertEqual(bot.ultimo_estado_navegacion, "CAPTCHA_SOLICITADO")
        self.assertEqual(boton.clicks, 1)

        resultado = bot._esperar_busqueda_habilitada("23331202202089")

        self.assertIs(resultado, boton)
        self.assertEqual(bot.ultimo_estado_navegacion, "BUSQUEDA_HABILITADA")

    def test_timeout_del_click_inicial_queda_auditado(self):
        bot = self.crear_bot(
            captcha_timeout_ms=300000,
            captcha_render_timeout_ms=0,
        )
        bot.page = PaginaEsperaFalsa()
        campo = CampoFalso("23331-2022-02089")
        boton = BotonFalso(habilitado=False)
        bot._input_causa_unico = lambda: campo
        bot._boton_buscar_unico = lambda: boton
        bot.ultimo_estado_navegacion = "ESPERAR_FIN_CAPTCHA"

        with self.assertRaisesRegex(
            PlaywrightTimeoutError, "BUSCAR_INICIAL_TIMEOUT_HABILITACION"
        ):
            bot._activar_captcha_con_click_inicial(
                "23331202202089", "intento:busqueda-1"
            )

        self.assertEqual(bot.ultimo_estado_navegacion, "CAPTCHA_TIMEOUT")
        self.assertEqual(boton.clicks, 0)
        self.assertTrue(bot._captcha_reinicio_buscador_pendiente)

    def test_siguiente_causa_recarga_formulario_tras_fallo_captcha(self):
        bot = self.crear_bot()
        bot._captcha_reinicio_buscador_pendiente = True
        recargas = []
        validaciones = []
        bot._reload_navegacion = (
            lambda contexto, **kwargs: recargas.append((contexto, kwargs))
        )
        bot._esperar_buscador_listo = (
            lambda causa: validaciones.append(causa) or {"listo": True}
        )

        reiniciado = bot._reiniciar_buscador_si_fallo_captcha("12331202300942")

        self.assertTrue(reiniciado)
        self.assertEqual(len(recargas), 1)
        self.assertEqual(recargas[0][0], "reiniciar_formulario_tras_fallo_captcha")
        self.assertEqual(recargas[0][1]["wait_until"], "domcontentloaded")
        self.assertEqual(validaciones, ["12331202300942"])
        self.assertFalse(bot._captcha_reinicio_buscador_pendiente)

    def test_modo_api_resuelve_inyecta_y_confirma_angular(self):
        class ProveedorFalso:
            def __init__(self):
                self.disponibilidad = 0
                self.resoluciones = 0

            def comprobar_disponibilidad(self):
                self.disponibilidad += 1
                return {"disponible": True, "saldo_usd": 1.0}

            def resolver(self, desafio, contexto):
                self.resoluciones += 1
                return CaptchaSolucion("token-secreto", 77, "2captcha", 5000, 0.1)

        proveedor = ProveedorFalso()
        bot = BotJudicial(
            "https://ejemplo.local",
            captcha={"modo": "api_supervisada"},
            proveedor_captcha=proveedor,
        )
        desafio = CaptchaDesafio(
            "recaptcha_v2", "https://ejemplo.local", "sitekey", "0"
        )
        aplicadas = []
        bot._obtener_desafio_captcha = lambda causa: (desafio, "huella")
        bot._aplicar_solucion_captcha = (
            lambda causa, recibido, solucion: aplicadas.append(
                (causa, recibido.widget_id, solucion.task_id)
            ) or {"aplicado": True}
        )
        bot._esperar_busqueda_habilitada = lambda causa: "boton"

        resultado = bot._resolver_o_esperar_captcha(
            "23331202202089", "intento:busqueda-1"
        )

        self.assertEqual(resultado, "boton")
        self.assertEqual(proveedor.disponibilidad, 1)
        self.assertEqual(proveedor.resoluciones, 1)
        self.assertEqual(aplicadas, [("23331202202089", "0", 77)])
        self.assertEqual(bot._captcha_tareas_por_causa["23331202202089"], 1)

    def test_clave_ausente_da_espera_humana_limitada_sin_abrir_circuito(self):
        bot = BotJudicial(
            "https://ejemplo.local",
            captcha={
                "modo": "api_con_espera_humana_limitada",
                "api_key_env": "VARIABLE_CAPTCHA_INEXISTENTE_TEST",
                "espera_humana_maxima_ms": 60000,
            },
        )
        esperas = []
        bot._esperar_busqueda_habilitada = (
            lambda causa, **kwargs: esperas.append((causa, kwargs)) or "boton"
        )

        with patch.dict("os.environ", {}, clear=True):
            resultado = bot._resolver_o_esperar_captcha(
                "23331202202089", "intento:busqueda-1"
            )

        self.assertEqual(resultado, "boton")
        self.assertEqual(
            esperas,
            [(
                "23331202202089",
                {
                    "timeout_ms": 30000,
                    "accion_timeout": "espera_humana_limitada_expirada",
                    "codigo_timeout": "CAPTCHA_ESPERA_MANUAL_30S_AGOTADA",
                },
            )],
        )
        self.assertEqual(bot._captcha_errores_consecutivos, 0)
        self.assertFalse(bot._captcha_circuito_abierto)

    def test_modo_manual_ya_no_esta_admitido(self):
        bot = BotJudicial("https://ejemplo.local", captcha={"modo": "manual"})

        with self.assertRaisesRegex(
            CaptchaConfiguracionError, "CAPTCHA_MODO_MANUAL_NO_ADMITIDO"
        ):
            bot._resolver_o_esperar_captcha(
                "23331202202089", "intento:busqueda-1"
            )

    def test_timeout_api_supervisada_no_encadena_espera_manual(self):
        class ProveedorTimeout:
            def comprobar_disponibilidad(self):
                return {"disponible": True, "saldo_usd": 1.0}

            def resolver(self, desafio, contexto):
                raise CaptchaResolucionTimeout(
                    "CAPTCHA_RESOLUCION_TIMEOUT", recuperable=True
                )

        bot = BotJudicial(
            "https://ejemplo.local",
            captcha={
                "modo": "api_supervisada",
                "fallback_manual": False,
            },
            proveedor_captcha=ProveedorTimeout(),
        )
        desafio = CaptchaDesafio(
            "recaptcha_v2", "https://ejemplo.local", "sitekey", "0"
        )
        bot._obtener_desafio_captcha = lambda causa: (desafio, "huella")
        esperas_manuales = []
        bot._esperar_busqueda_habilitada = (
            lambda causa: esperas_manuales.append(causa) or "boton"
        )

        with self.assertRaisesRegex(
            CaptchaResolucionTimeout, "CAPTCHA_RESOLUCION_TIMEOUT"
        ):
            bot._resolver_o_esperar_captcha(
                "23331202202089", "intento:busqueda-1"
            )

        self.assertEqual(esperas_manuales, [])
        self.assertTrue(bot._captcha_reinicio_buscador_pendiente)
        self.assertEqual(bot._captcha_errores_consecutivos, 1)

    def test_buscar_hace_un_solo_clic_por_intento(self):
        bot = self.crear_bot()
        campo = CampoFalso("23331-2022-02089")
        boton = BotonFalso()
        bot._input_causa_unico = lambda: campo
        bot._boton_buscar_unico = lambda: boton
        bot._captcha_visible = lambda: False

        bot._enviar_busqueda_una_vez("23331202202089", "intento-1")

        self.assertEqual(boton.clicks, 1)
        with self.assertRaisesRegex(RuntimeError, "DOBLE_CLICK_BUSCAR_BLOQUEADO"):
            bot._enviar_busqueda_una_vez("23331202202089", "intento-1")
        self.assertEqual(boton.clicks, 1)

    def test_buscar_deshabilitado_no_hace_clic(self):
        bot = self.crear_bot(captcha_timeout_ms=0)
        campo = CampoFalso("23331202202089")
        boton = BotonFalso(habilitado=False)
        bot._input_causa_unico = lambda: campo
        bot._boton_buscar_unico = lambda: boton
        bot._captcha_visible = lambda: True
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None

        with self.assertRaises(PlaywrightTimeoutError):
            bot._esperar_busqueda_habilitada("23331202202089")
        self.assertEqual(boton.clicks, 0)

    def test_resultados_elige_solo_fila_de_causa_canonica(self):
        filas = [
            FilaFalsa("1 14/06/2022 23331202202088 COBRO"),
            FilaFalsa("2 15/06/2022 23331202202089 COBRO"),
        ]
        bot = self.crear_bot()
        bot.page = PaginaFilasFalsa(filas)

        coincidencias = bot._filas_resultado_coincidentes("23331-2022-02089")

        self.assertEqual(coincidencias, [filas[1]])

    def test_resultados_excluye_sufijo_alfanumerico(self):
        filas = [
            FilaFalsa("1 14/03/2017 12331201700065G INSPECCION"),
            FilaFalsa("2 23/01/2017 12331201700065 COBRO"),
        ]
        bot = self.crear_bot()
        bot.page = PaginaFilasDivFalsa(filas)

        coincidencias = bot._filas_resultado_coincidentes("12331-2017-00065")

        self.assertEqual(coincidencias, [filas[1]])
        self.assertIn(".causa-individual", bot.page.ultimo_selector)

    def test_resultados_admite_trece_digitos_y_excluye_sufijo(self):
        filas = [
            FilaFalsa("1 10/08/2014 1233120140845G INSPECCION"),
            FilaFalsa("2 10/08/2014 1233120140845 COBRO"),
        ]
        bot = self.crear_bot()
        bot.page = PaginaFilasDivFalsa(filas)

        coincidencias = bot._filas_resultado_coincidentes("12331-2014-0845")

        self.assertEqual(coincidencias, [filas[1]])

    def test_reconoce_rechazo_explicito_del_formulario(self):
        self.assertEqual(
            BotJudicial._motivo_rechazo_formulario(
                "El formulario contiene errores. Revise los campos marcados."
            ),
            "FORMULARIO_CONTIENE_ERRORES",
        )

    def test_notificacion_sin_resultados_exige_verificacion_manual(self):
        bot = self.crear_bot()
        bot.page = PaginaMensajeFalsa("La consulta no devolvi\u00f3 resultados.")
        bot.ultimo_estado_navegacion = "BUSQUEDA_ENVIADA"

        resultado = bot._esperar_resultados("1233120161181")

        self.assertEqual(resultado, "VERIFICACION_MANUAL_SIN_RESULTADOS")
        self.assertEqual(bot.ultimo_estado_navegacion, "VERIFICACION_MANUAL")

    def test_apertura_de_causas_usa_enlace_de_fila_numerica(self):
        pagina = PaginaAperturaCausaFalsa()
        enlace_g = EnlaceFalso(
            "Vinculo para ingresar a los movimientos del proceso 12331201700065G"
        )
        enlace_numerico = EnlaceFalso(
            "Vinculo para ingresar a los movimientos del proceso 12331201700065",
            lambda: setattr(pagina, "url", "https://ejemplo.local/movimientos"),
        )
        fila_numerica = FilaCausaFalsa("12331201700065", enlace_numerico)
        bot = self.crear_bot()
        bot.page = pagina
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None

        bot._abrir_detalle_causa("12331201700065", fila_numerica)

        self.assertEqual(enlace_numerico.clicks, 1)
        self.assertEqual(enlace_g.clicks, 0)
        self.assertEqual(pagina.detalle.clicks, 1)

    def test_flujo_transaccional_abre_movimientos_en_fila_seleccionada(self):
        pagina = PaginaAperturaCausaFalsa()
        enlace_numerico = EnlaceFalso(
            "Vinculo para ingresar a los movimientos del proceso 12331201700065",
            lambda: setattr(pagina, "url", "https://ejemplo.local/movimientos"),
        )
        fila_numerica = FilaCausaFalsa("12331201700065", enlace_numerico)
        bot = self.crear_bot()
        bot.page = pagina
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None
        bot._click_navegacion = lambda control, accion: control.click()

        bot._abrir_movimientos_causa("12331201700065", fila_numerica)

        self.assertEqual(enlace_numerico.clicks, 1)
        self.assertEqual(pagina.url, "https://ejemplo.local/movimientos")

    def test_apertura_carpeta_no_depende_del_load_global_de_actuaciones(self):
        bot = self.crear_bot()
        bot.page = PaginaCargaGlobalPendienteFalsa()
        descriptor = {"clave_carpeta": "12331202500604:UNICA"}
        enlace = BotonFalso()
        resultado_carpeta = {
            "estado": "COMPLETA",
            "datos": {"HISTORIAL_ACTUACIONES": []},
        }
        validaciones = []
        bot._esperar_movimientos_listos = lambda causa: None
        bot._descubrir_carpetas_procesales = lambda causa: [descriptor]
        bot._localizar_carpeta_procesal = lambda causa, buscado: (None, enlace)
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None
        bot._click_navegacion = lambda control, contexto: control.click()
        bot._esperar_informacion_proceso_y_bloquear = (
            lambda causa, buscado, secuencia: validaciones.append(
                (causa, buscado, secuencia)
            ) or "token"
        )
        bot._extraer_informacion_proceso = (
            lambda causa, buscado, secuencia, token: resultado_carpeta
        )
        bot._volver_a_movimientos = lambda causa: None
        bot._consolidar_resultados_carpetas = (
            lambda causa, resultados: {"causa": causa, "carpetas": resultados}
        )

        resultado = bot._procesar_todas_las_carpetas("12331202500604")

        self.assertEqual(enlace.clicks, 1)
        self.assertEqual(validaciones, [("12331202500604", descriptor, 0)])
        self.assertEqual(resultado["carpetas"], [resultado_carpeta])

    def test_api_completa_evade_render_lento_de_actuaciones(self):
        causa = "23331202202089"
        bot = self.crear_bot(quietud_api_ms=250)
        bot.page = PaginaActuacionesApiFalsa()
        bot._secuencia_api = 8
        bot._ultima_respuesta_api_monotonic = 9.0
        bot.paquetes_api_interceptados = [{
            "secuencia": 8,
            "capturado_monotonic": 9.0,
            "url": "https://portal/api/actuacionesJudiciales",
            "data": [{
                "idJuicio": causa,
                "fecha": "2025-01-01T10:00:00Z",
                "actividad": "CITACION REALIZADA",
            }],
        }]
        bot.ultimo_estado_navegacion = "INFORMACION_PROCESO_CARGANDO"
        bot._intento_actual = "intento-rapido"
        descriptor = {"clave_carpeta": "carpeta-1"}

        with patch("src.motor_busqueda_web.monotonic", return_value=10.0):
            token = bot._esperar_informacion_proceso_y_bloquear(
                causa, descriptor, 7
            )
            firma = bot._esperar_actuaciones_estables(causa, 7)

        self.assertEqual(firma[1], "API_ACTUACIONES")
        self.assertEqual(firma[2], 1)
        self.assertIn("carpeta-1", token)
        self.assertEqual(bot.page.esperas, [])

    def test_via_rapida_api_rechaza_actuaciones_de_otra_causa(self):
        bot = self.crear_bot(quietud_api_ms=250)
        bot._secuencia_api = 4
        bot.paquetes_api_interceptados = [{
            "secuencia": 4,
            "capturado_monotonic": 9.0,
            "url": "https://portal/api/actuacionesJudiciales",
            "data": [{
                "idJuicio": "23331202202088",
                "actividad": "ACTUACION AJENA",
            }],
        }]

        with patch("src.motor_busqueda_web.monotonic", return_value=10.0):
            firma = bot._firma_api_actuaciones_lista("23331202202089", 3)

        self.assertIsNone(firma)

    def test_flujo_transaccional_rechaza_fila_con_sufijo(self):
        pagina = PaginaAperturaCausaFalsa()
        fila_g = FilaCausaFalsa("12331201700065G", EnlaceFalso("movimientos"))
        bot = self.crear_bot()
        bot.page = pagina
        bot._cambiar_estado_navegacion = lambda *args, **kwargs: None

        with self.assertRaisesRegex(RuntimeError, "FILA_NO_CORRESPONDE_A_CAUSA"):
            bot._abrir_movimientos_causa("12331201700065", fila_g)

    def test_paquetes_descarta_otra_causa(self):
        bot = self.crear_bot()
        paquetes = [
            {
                "url": "https://portal/api/actuaciones",
                "data": {"idJuicio": "23331202202089", "actuaciones": []},
            },
            {
                "url": "https://portal/api/actuaciones",
                "data": {"idJuicio": "23331202202088", "actuaciones": []},
            },
        ]

        seleccionados = bot._paquetes_api_de_carpeta(paquetes, "23331-2022-02089")

        self.assertEqual(seleccionados, [paquetes[0]])


if __name__ == "__main__":
    unittest.main()
