# src/agente_explorador.py
import os
from time import monotonic
import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from src.logger_config import obtener_logger

logger = obtener_logger("AgenteExplorador")


class AgenteExplorador:
    """
    Agente Explorador con dos rutas de extracción:
    - Primaria: captura XHR/fetch JSON y lo convierte inmediatamente a DataFrame.
    - Respaldo: descarga el DOM sólo si la captura de red no es utilizable.
    """
    TIPOS_RECURSO_ESTATICO = frozenset({"image", "stylesheet", "font"})
    EXTENSIONES_ESTATICAS = (".png", ".jpg", ".jpeg", ".svg", ".css", ".woff", ".woff2", ".ttf")
    PATRONES_API_JUDICATURA = (
        "/api/expedientes",
        "/api/actuaciones",
        "/api/procesos",
        "/api/causas",
    )
    TIMEOUT_XHR_MS = 15_000
    TIMEOUT_CAPTCHA_MS = 300_000

    def __init__(
        self,
        url_portal="https://procesosjudiciales.funcionjudicial.gob.ec/busqueda-filtros",
        dir_temp="temp_htmls",
        modo_visible=False,
        patrones_api=None,
    ):
        self.url_portal = url_portal
        self.dir_temp = dir_temp
        os.makedirs(self.dir_temp, exist_ok=True)
        self.patrones_api = tuple(patron.lower() for patron in (patrones_api or self.PATRONES_API_JUDICATURA))
        self.paquetes_json_api = []
        self.captura_api_actual = None
        self.df_api_actual = None
        self.error_api_actual = None

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=not modo_visible,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--ignore-certificate-errors",
            ],
            ignore_default_args=["--enable-automation"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            ignore_https_errors=True
        )
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-EC', 'es', 'en-US', 'en'] });
        """)
        self.page = self.context.new_page()

        # Estas reglas se activan antes de visitar la SPA.
        self.page.route("**/*", self._bloquear_recursos_estaticos)
        self.page.on("response", self._interceptar_respuesta_api)

        logger.info(f"Agente Explorador iniciado en {self.url_portal} (Headless: {not modo_visible}, Dir HTML: {self.dir_temp})")
        self.page.goto(self.url_portal, timeout=60000, wait_until="domcontentloaded")

    def _bloquear_recursos_estaticos(self, route):
        """Aborta recursos que no aportan datos al procesamiento de expedientes."""
        request = route.request
        url_sin_query = request.url.lower().split("?", 1)[0]
        if (
            request.resource_type in self.TIPOS_RECURSO_ESTATICO
            or url_sin_query.endswith(self.EXTENSIONES_ESTATICAS)
        ):
            route.abort()
            return
        route.continue_()

    def _es_respuesta_api_juicio(self, response):
        """Filtro estricto para respuestas JSON propias de expedientes judiciales."""
        return (
            response.request.resource_type in {"xhr", "fetch"}
            and response.status == 200
            and any(patron in response.url.lower() for patron in self.patrones_api)
        )

    def _es_respuesta_api_o_error_juicio(self, response):
        """Incluye errores HTTP para que puedan ser auditados antes del respaldo DOM."""
        return (
            response.request.resource_type in {"xhr", "fetch"}
            and any(patron in response.url.lower() for patron in self.patrones_api)
        )

    def _reiniciar_captura_api(self):
        self.paquetes_json_api.clear()
        self.captura_api_actual = None
        self.df_api_actual = None
        self.error_api_actual = None

    @staticmethod
    def _dataframe_desde_json(payload):
        """Convierte el payload nativo a DataFrame y normaliza sus cabeceras de inmediato."""
        datos = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(datos, dict):
            df = pd.json_normalize([datos])
        elif isinstance(datos, list):
            df = pd.json_normalize(datos)
        else:
            raise ValueError("El payload XHR no contiene un objeto o lista JSON tabulable.")

        df.columns = df.columns.astype(str).str.strip().str.upper()
        if df.empty:
            raise ValueError("El payload XHR fue capturado, pero no contiene registros.")
        return df

    def _interceptar_respuesta_api(self, response):
        """Listener pasivo: captura sólo respuestas XHR/fetch válidas de la API judicial."""
        if not self._es_respuesta_api_juicio(response):
            return

        try:
            payload = response.json()
            captura = {"url": response.url, "payload": payload}
            df = self._dataframe_desde_json(captura["payload"])
            self.captura_api_actual = captura
            self.df_api_actual = df
            self.paquetes_json_api[:] = [captura]
            self.error_api_actual = None
            logger.info("[API XHR] JSON capturado desde %s (%s registros).", response.url, len(df))
        except Exception as e:
            self.error_api_actual = f"Respuesta XHR no utilizable: {e}"
            logger.warning("%s", self.error_api_actual)

    def procesar_datos_api_con_pandas(self):
        """Devuelve el DataFrame creado en el listener, sin reprocesar el JSON original."""
        return self.df_api_actual

    def obtener_payload_api(self):
        """Retorna el payload JSON original, fuente de verdad de la ruta primaria."""
        return self.captura_api_actual["payload"] if self.captura_api_actual else None

    def obtener_error_api(self):
        """Expone el motivo de fallo de la captura para la auditoría transaccional."""
        return self.error_api_actual

    def regresar_al_buscador(self):
        """Regresa al buscador utilizando esperas explícitas condicionales."""
        try:
            input_busqueda = self.page.locator("input[placeholder*='códigoDependencia-Año-Secuencial'], input[formcontrolname='numeroJuicio']").first
            if input_busqueda.is_visible():
                return True

            btn_filtros = self.page.locator("button:has-text('Filtros de búsqueda'), a:has-text('Filtros de búsqueda')").first
            btn_regresar = self.page.locator("button:has-text('Regresar'), a:has-text('Regresar')").first

            for _ in range(3):
                if input_busqueda.is_visible():
                    break
                if btn_filtros.is_visible():
                    btn_filtros.click()
                    self.page.wait_for_selector("input[placeholder*='códigoDependencia-Año-Secuencial']", state="visible", timeout=3000)
                elif btn_regresar.is_visible():
                    btn_regresar.click()
                    self.page.wait_for_selector("input[placeholder*='códigoDependencia-Año-Secuencial']", state="visible", timeout=3000)
                else:
                    self.page.go_back()
                    self.page.wait_for_load_state("domcontentloaded")
            return True
        except Exception as e:
            logger.warning(f"Error al regresar al buscador: {e}")
            self.page.goto(self.url_portal, wait_until="domcontentloaded")
            return False

    def descargar_html_juicio(self, numero_causa):
        """
        Ejecuta primero la ruta primaria XHR/JSON. Sólo devuelve una ruta HTML
        cuando debe delegar el procesamiento a la ruta de respaldo DOM.
        """
        causa_str = str(numero_causa).strip()
        ruta_html = os.path.join(self.dir_temp, f"{causa_str}.html")
        self._reiniciar_captura_api()

        logger.info("Iniciando ruta primaria XHR/JSON para causa: %s", causa_str)

        try:
            selector_input_busqueda = "input[placeholder*='códigoDependencia-Año-Secuencial'], input[formcontrolname='numeroJuicio']"
            input_causa = self.page.locator(selector_input_busqueda).first

            if not input_causa.is_visible():
                if "busqueda" not in self.page.url.lower():
                    self.page.goto(self.url_portal, wait_until="domcontentloaded")
                else:
                    self.regresar_al_buscador()

            self.page.wait_for_selector(selector_input_busqueda, state="visible", timeout=10000)
            input_causa.click()
            input_causa.fill("")
            input_causa.press_sequentially(causa_str, delay=15)
            input_causa.dispatch_event("input")
            input_causa.dispatch_event("change")
            logger.info("[FASE 1] Causa '%s' ingresada. Esperando respuesta XHR/fetch...", causa_str)

            btn_buscar = self.page.get_by_role("button", name="BUSCAR", exact=True)
            if btn_buscar.count() != 1:
                raise RuntimeError("BOTON_BUSCAR_AMBIGUO_O_AUSENTE")

            limite = monotonic() + (self.TIMEOUT_CAPTCHA_MS / 1000)
            estable = 0
            selector_captcha = (
                "iframe[src*='captcha'], iframe[title*='captcha' i], "
                "[class*='captcha' i], [id*='captcha' i], "
                "[class*='challenge' i], [id*='challenge' i], [role='dialog']"
            )
            while monotonic() < limite:
                captcha_visible = False
                try:
                    captcha = self.page.locator(selector_captcha)
                    captcha_visible = any(captcha.nth(i).is_visible() for i in range(captcha.count()))
                except Exception:
                    pass

                if (
                    btn_buscar.is_visible()
                    and btn_buscar.is_enabled()
                    and btn_buscar.get_attribute("aria-disabled") != "true"
                    and not captcha_visible
                ):
                    estable += 1
                    if estable >= 2:
                        break
                else:
                    estable = 0
                self.page.wait_for_timeout(250)
            else:
                self.error_api_actual = "CAPTCHA_TIMEOUT: BUSCAR no qued? habilitado."
                logger.warning("[NAVEGACION_ESATJE] %s", self.error_api_actual)
                return None

            with self.page.expect_response(
                self._es_respuesta_api_o_error_juicio,
                timeout=self.TIMEOUT_XHR_MS,
            ) as respuesta_esperada:
                btn_buscar.click()

            respuesta = respuesta_esperada.value
            if respuesta.status != 200:
                self.error_api_actual = f"La API judicial respondió HTTP {respuesta.status}."
            # El listener ya procesa la respuesta; esta llamada sólo cubre adaptadores o mocks sin eventos.
            elif self.df_api_actual is None:
                self._interceptar_respuesta_api(respuesta)

            if self.df_api_actual is not None:
                logger.info("[RUTA PRIMARIA] Captura XHR/JSON completada para causa %s.", causa_str)
                return None

            self.error_api_actual = self.error_api_actual or "La respuesta XHR no produjo un DataFrame utilizable."
        except PlaywrightTimeoutError:
            self.error_api_actual = (
                f"Timeout de {self.TIMEOUT_XHR_MS} ms esperando una respuesta XHR/fetch judicial."
            )
        except Exception as e:
            self.error_api_actual = f"Error durante la captura XHR/fetch: {e}"

        logger.warning(
            "[RUTA PRIMARIA FALLIDA] Causa %s: %s. Activando respaldo DOM.",
            causa_str,
            self.error_api_actual,
        )
        return self._descargar_html_respaldo(causa_str, ruta_html)

    def _descargar_html_respaldo(self, causa_str, ruta_html):
        """Ruta DOM usada únicamente cuando la captura XHR/fetch falla."""
        try:
            logger.info("[RUTA RESPALDO DOM] Buscando expediente para causa %s.", causa_str)
            texto_actual = self.page.inner_text("body")
            causa_canonica = "".join(caracter for caracter in causa_str if caracter.isdigit())
            texto_canonico = "".join(caracter for caracter in texto_actual if caracter.isdigit())
            if "DATOS GENERALES" not in texto_actual.upper() or causa_canonica not in texto_canonico:
                raise RuntimeError(
                    "NAVEGACION_RELATIVA_REQUERIDA: la ruta de respaldo no abre carpetas globales."
                )

            selector_freno_estricto = "text=/Actor\\/Ofendido:|Información del proceso|Actuaciones Judiciales|Exportar PDF/i"
            self.page.wait_for_selector(selector_freno_estricto, state="visible", timeout=15000)

            contenido_html = self.page.content()
            with open(ruta_html, "w", encoding="utf-8") as archivo_html:
                archivo_html.write(contenido_html)

            logger.info("[RESPALDO DOM] HTML capturado en: %s (%s bytes)", ruta_html, len(contenido_html))
            return ruta_html
        except Exception as e:
            logger.error("Fallo en la ruta de respaldo DOM para causa %s: %s", causa_str, e)
            return None

    def cerrar(self):
        """Cierra el navegador y Playwright."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Agente Explorador cerrado.")
