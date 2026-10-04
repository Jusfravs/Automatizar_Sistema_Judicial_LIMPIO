# src/motor_busqueda_web.py
import hashlib
import os
import re
import json
from datetime import datetime
from time import monotonic
from traceback import format_exc
import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from src.agente_extractor import (
    AgenteExtractor, NavegadorArbolContenido, normalizar_texto,
)
from src.catalogo_procesal import enriquecer_datos_procesales
from src.logger_config import obtener_logger
from src.validacion_pertenencia import ESTADO_EXCLUIDO, validar_pertenencia_cartera
from src.servicio_captcha import (
    CaptchaConfiguracionError, CaptchaDesafio, CaptchaError,
    CaptchaProveedorError, Proveedor2Captcha,
)

# Intentar soporte opcional de YAML para keywords configurables
try:
    import yaml
    _YAML_AVAILABLE = True
except Exception:
    _YAML_AVAILABLE = False

logger = obtener_logger("BotJudicial")


def _load_extraction_keywords():
    """Carga una lista de keywords desde rutas conocidas o desde un archivo YAML/TSV simple.
    Busca en (en este orden): env(EXTRACTION_KEYWORDS_PATH), config/extraction_keywords.yml,
    data/extraction_keywords.yml, extraction_keywords.yml. Devuelve lista de strings en minúsculas.
    """
    candidates = [
        os.environ.get("EXTRACTION_KEYWORDS_PATH"),
        os.path.join("config", "extraction_keywords.yml"),
        os.path.join("data", "extraction_keywords.yml"),
        "extraction_keywords.yml",
    ]
    for p in candidates:
        if not p:
            continue
        try:
            if os.path.exists(p):
                if _YAML_AVAILABLE:
                    with open(p, "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh)
                    if isinstance(data, dict):
                        kws = []
                        for v in data.values():
                            if isinstance(v, list):
                                kws.extend([str(x) for x in v])
                            elif isinstance(v, str):
                                kws.append(v)
                        return [k.lower() for k in kws if k]
                    elif isinstance(data, list):
                        return [str(x).lower() for x in data if x]
                else:
                    # fallback: leer líneas no comentadas
                    with open(p, "r", encoding="utf-8") as fh:
                        lines = [l.strip() for l in fh.readlines()]
                    lines = [l for l in lines if l and not l.startswith("#")]
                    return [l.lower() for l in lines]
        except Exception:
            continue

    # Default conservative set
    return [
        'mandam', 'mandamiento', 'mandamiento de ejecucion', 'auto de ejecucion', 'auto de ejecucion', 'auto de cumplimiento'
    ]


class BotJudicial:
    """
    Motor RPA Asistido con Arquitectura de Ejecución Dual para e-SATJE:
    1. Ruta Principal (API Fetching Nivel Dios 🚀): Intercepta respuestas JSON vía page.on('response'),
       bypass completo de BeautifulSoup4, tabulación vectorizada con Pandas y persistencia directa.
    2. Ruta de Respaldo (Sincronización DOM): Freno de ejecución con wait_for_selector('text="Actor/Ofendido:"')
       para asegurar inyección en Angular antes de enviar el HTML a BeautifulSoup4.
    """
    def __init__(self, url_portal, navegacion=None, captcha=None, proveedor_captcha=None):
        self.url_portal = url_portal
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.extractor = AgenteExtractor()
        self.nav_arbol = NavegadorArbolContenido()
        self.paquetes_api_interceptados = []
        self.datos_extraidos = None
        self.navegacion = {
            "captcha_timeout_ms": 300000,
            "captcha_render_timeout_ms": 15000,
            "resultados_timeout_ms": 30000,
            "datos_generales_timeout_ms": 30000,
            "actuaciones_timeout_ms": 30000,
            "pantalla_final_timeout_ms": 30000,
            "pantalla_final_estabilizacion_ms": 1500,
            "max_reintentos_transicion": 2,
        }
        self.navegacion.update(navegacion or {})
        self.captcha_config = {
            "modo": "api_con_espera_humana_limitada",
            "proveedor": "2captcha",
            "api_key_env": "AUTOCAPTCHA_API_KEY",
            "http_timeout_ms": 10000,
            "max_intentos_red": 3,
            "reintento_red_ms": 1000,
            "resolucion_timeout_ms": 300000,
            "sondeo_ms": 5000,
            "confirmacion_inyeccion_timeout_ms": 10000,
            # El token ya fue inyectado y el botón validado; solo se deja un
            # margen corto para que Angular estabilice el formulario.
            "espera_post_solucion_ms": 500,
            "max_tareas_por_causa": 2,
            "max_errores_consecutivos": 3,
            "saldo_minimo_usd": 0.01,
            # La intervencion humana nunca es un modo de operacion: solo es
            # una ventana breve de contingencia despues de un fallo de la API.
            "espera_humana_maxima_ms": 30000,
            "reportar_incorrecta": True,
            "reportar_correcta": True,
        }
        self.captcha_config.update(captcha or {})
        self.proveedor_captcha = proveedor_captcha
        self._captcha_disponibilidad_verificada = False
        self._captcha_tareas_por_causa = {}
        self._captcha_tareas_activas = set()
        self._captcha_errores_consecutivos = 0
        self._captcha_circuito_abierto = False
        self._captcha_solucion_actual = None
        self._captcha_reinicio_buscador_pendiente = False
        self.ultimo_estado_navegacion = None
        self._busquedas_enviadas = set()

    def iniciar_navegador(self, modo_visible=True):
        """Inicia el navegador Chromium con bypass anti-automatización para F5 WAF y listener API."""
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
        self.context.add_init_script("""
            (() => {
                if (window.__botCaptchaHookInstalado) return;
                window.__botCaptchaHookInstalado = true;
                window.__botCaptchaCallbacks = {};
                const instalar = () => {
                    const api = window.grecaptcha;
                    if (!api || typeof api.render !== 'function' || api.render.__botEnvuelto) {
                        return;
                    }
                    const renderOriginal = api.render.bind(api);
                    const renderEnvuelto = function(contenedor, parametros, heredar) {
                        const opciones = Object.assign({}, parametros || {});
                        const callbackOriginal = opciones.callback;
                        let widgetId = null;
                        const resolverCallback = () => {
                            if (typeof callbackOriginal === 'function') return callbackOriginal;
                            if (typeof callbackOriginal === 'string' &&
                                typeof window[callbackOriginal] === 'function') {
                                return window[callbackOriginal];
                            }
                            return null;
                        };
                        opciones.callback = function(token) {
                            const registro = window.__botCaptchaCallbacks[String(widgetId)];
                            if (registro) registro.ultimaRespuesta = Date.now();
                            const callback = resolverCallback();
                            if (callback) return callback.apply(this, arguments);
                        };
                        widgetId = renderOriginal(contenedor, opciones, heredar);
                        const contenedorId = typeof contenedor === 'string'
                            ? contenedor
                            : ((contenedor && contenedor.id) || null);
                        window.__botCaptchaCallbacks[String(widgetId)] = {
                            widgetId: String(widgetId),
                            contenedorId: contenedorId,
                            sitekey: String(opciones.sitekey || ''),
                            callback: opciones.callback,
                            callbackOriginalDisponible: Boolean(resolverCallback()),
                            inyectadoPorBot: false,
                            ultimaRespuesta: null
                        };
                        return widgetId;
                    };
                    renderEnvuelto.__botEnvuelto = true;
                    api.render = renderEnvuelto;
                };
                let callbackCarga = null;
                try {
                    const callbackPrevio = window.ngx_captcha_onload_callback;
                    if (typeof callbackPrevio === 'function') callbackCarga = callbackPrevio;
                    Object.defineProperty(window, 'ngx_captcha_onload_callback', {
                        configurable: true,
                        get: () => {
                            if (typeof callbackCarga !== 'function') return callbackCarga;
                            return function() {
                                instalar();
                                return callbackCarga.apply(this, arguments);
                            };
                        },
                        set: (valor) => {
                            callbackCarga = valor;
                        }
                    });
                } catch (_) {
                    // El sondeo inferior permanece como respaldo si el host no permite el descriptor.
                }
                instalar();
                const temporizador = window.setInterval(instalar, 10);
                window.addEventListener('beforeunload', () => window.clearInterval(temporizador));
            })();
        """)
        self.page = self.context.new_page()
        
        # Ruta Principal: Listener de intercepción de red (API Fetching)
        self.page.on("response", self._interceptar_respuesta_api)
        
        logger.info("Navegador iniciado en %s", self.url_portal)
        self.page.goto(self.url_portal, timeout=60000, wait_until="domcontentloaded")
        
        # Aguardar la resolución pasiva del reto F5 WAF y renderizado de la UI Angular
        try:
            self.page.wait_for_selector(
                "input[placeholder*='códigoDependencia-Año-Secuencial'], input[formcontrolname='numeroJuicio'], button:has-text('BUSCAR')",
                state="visible",
                timeout=20000
            )
            logger.info("[OK] Portal del Consejo de la Judicatura cargado correctamente.")
        except Exception:
            logger.warning("[!] La UI de búsqueda tardó en aparecer; continuando observación.")

    def asegurar_navegador_vivo(self, modo_visible=True):
        """
        Verifica si la página y el contexto del navegador están activos.
        Si se cerró el navegador (Target page, context or browser has been closed),
        lo relanza automáticamente sin interrumpir la ejecución masiva.
        """
        try:
            if not self.page or self.page.is_closed() or not self.browser or not self.browser.is_connected():
                logger.warning("[!] El navegador o la pestaña fue cerrada. Relanzando automáticamente...")
                self.cerrar_navegador()
                self.iniciar_navegador(modo_visible=modo_visible)
                return True
        except Exception:
            logger.warning("[!] Error al verificar estado del navegador. Reiniciando instancia de Playwright...")
            self.cerrar_navegador()
            self.iniciar_navegador(modo_visible=modo_visible)
            return True
        return False

    def _verificar_sesion_activa(self):
        """
        Verifica si la sesión del portal sigue activa y el navegador está vivo.
        Si detecta expiración o cierre, relanza la navegación.
        """
        self.asegurar_navegador_vivo(modo_visible=True)
        try:
            contenido = self.page.inner_text("body", timeout=5000)
            indicadores_expiracion = [
                "sesión expirada", "session expired", "iniciar sesión",
                "vuelva a ingresar", "token expirado", "no autorizado",
            ]
            for indicador in indicadores_expiracion:
                if indicador.lower() in contenido.lower():
                    logger.warning("[!] Sesión expirada detectada. Reiniciando navegación...")
                    self.page.goto(self.url_portal, timeout=60000, wait_until="domcontentloaded")
                    try:
                        self.page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    return False
        except Exception as e_verif:
            if "closed" in str(e_verif).lower():
                logger.warning("[!] Detectado navegador cerrado durante verificación. Relanzando...")
                self.asegurar_navegador_vivo(modo_visible=True)
        return True

    def _interceptar_respuesta_api(self, response):
        """
        Ruta Principal: Captura JSON puros de la API Angular de la Judicatura.
        """
        try:
            url = response.url.lower()
            if any(kw in url for kw in ["/api/", "expel", "proceso", "causa", "actuaciones", "catalogo"]):
                if not any(ext in url for ext in [".js", ".css", ".png", ".ico", ".woff", ".svg"]):
                    if response.status in [200, 201]:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = response.json()
                            self.paquetes_api_interceptados.append({
                                "url": response.url,
                                "data": data
                            })
                            logger.debug("[RUTA PRINCIPAL API] Capturado JSON desde: %s", response.url)
        except Exception:
            pass

    def regresar_al_buscador(self):
        """
        Navegación jerárquica hacia arriba conservando sesión.
        """
        try:
            self.nav_arbol.subir_nivel("Retornando al nivel raíz de búsqueda")
            input_busqueda = self.page.locator("input[placeholder*='códigoDependencia-Año-Secuencial']").first
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
        except Exception:
            self.page.goto(self.url_portal, wait_until="domcontentloaded")
            return False

    @staticmethod
    def _causa_canonica(numero_juicio):
        """Normaliza el numero de causa para comparar portal y archivo de origen."""
        return re.sub(r"\D", "", str(numero_juicio or ""))

    @classmethod
    def _texto_contiene_causa_numerica_exacta(cls, texto, causa):
        """Busca una causa numérica completa sin aceptar sufijos alfanuméricos."""
        objetivo = cls._causa_canonica(causa)
        patron = re.compile(
            r"(?<![0-9A-Za-z])\d{5}(?:[\s-]?\d){8,}(?![0-9A-Za-z])"
        )
        return any(
            cls._causa_canonica(coincidencia.group(0)) == objetivo
            for coincidencia in patron.finditer(str(texto or ""))
        )

    @classmethod
    def _fila_corresponde_causa(cls, fila, causa):
        """Valida primero la columna de proceso y conserva cualquier sufijo."""
        try:
            columnas = fila.locator(".numero-proceso")
            if columnas.count() == 1:
                valor = columnas.nth(0).inner_text().strip()
                return bool(re.fullmatch(r"[\d\s-]+", valor)) and (
                    cls._causa_canonica(valor) == cls._causa_canonica(causa)
                )
        except Exception:
            pass
        return cls._texto_contiene_causa_numerica_exacta(fila.inner_text(), causa)

    @staticmethod
    def _causa_para_formulario(numero_juicio):
        """Conserva el formato que exige la m?scara de e-SATJE al escribir la causa."""
        valor = str(numero_juicio or "").strip()
        if re.fullmatch(r"\d{5}-\d{4}-\d{4,}", valor):
            return valor
        causa = BotJudicial._causa_canonica(valor)
        if len(causa) >= 13:
            return f"{causa[:5]}-{causa[5:9]}-{causa[9:]}"
        return valor

    def _cambiar_estado_navegacion(self, causa, anterior, siguiente, accion, **extra):
        self.ultimo_estado_navegacion = siguiente
        evento = {
            "causa": self._causa_canonica(causa),
            "estado_anterior": anterior,
            "estado_siguiente": siguiente,
            "accion": accion,
            **extra,
        }
        logger.info("[NAVEGACION_ESATJE] %s", json.dumps(evento, ensure_ascii=False, default=str))

    def _input_causa_unico(self):
        selector = "input[formcontrolname='numeroCausa'], input[formcontrolname='numeroJuicio'], input[placeholder*='Dependencia' i], input[placeholder*='causa' i]"
        locator = self.page.locator(selector)
        if locator.count() != 1:
            raise RuntimeError("INPUT_CAUSA_AMBIGUO_O_AUSENTE")
        return locator.nth(0)

    def _boton_buscar_unico(self):
        boton = self.page.get_by_role("button", name=re.compile(r"^\s*BUSCAR\s*$", re.IGNORECASE))
        if boton.count() == 1:
            return boton.nth(0)

        respaldo = self.page.locator("button[type='submit']:has-text('BUSCAR'), button:has-text('BUSCAR')")
        if respaldo.count() != 1:
            raise RuntimeError("BOTON_BUSCAR_AMBIGUO_O_AUSENTE")
        return respaldo.nth(0)

    def _captcha_renderizado(self):
        """Confirma que Angular ya mont? el control CAPTCHA en el formulario."""
        respuestas = self.page.locator("textarea[name='g-recaptcha-response']")
        widgets = self.page.locator(
            "ngx-recaptcha2, .g-recaptcha, .h-captcha, "
            "iframe[title*='recaptcha' i], iframe[src*='recaptcha' i]"
        )
        return respuestas.count() > 0 or widgets.count() > 0

    def _captcha_visible(self):
        """Indica si el CAPTCHA visible a?n no tiene un token v?lido del operador."""
        respuestas = self.page.locator("textarea[name='g-recaptcha-response']")
        widgets = self.page.locator(
            "ngx-recaptcha2, .g-recaptcha, .h-captcha, "
            "iframe[title*='recaptcha' i], iframe[src*='recaptcha' i]"
        )
        if widgets.count() == 0 and respuestas.count() == 0:
            return False

        for indice in range(respuestas.count()):
            try:
                if respuestas.nth(indice).input_value().strip():
                    return False
            except Exception:
                continue
        return True

    @staticmethod
    def _boton_habilitado(boton):
        clases = boton.get_attribute("class") or ""
        etiqueta = boton.get_attribute("aria-label") or ""
        return (
            boton.is_visible()
            and boton.is_enabled()
            and boton.get_attribute("disabled") is None
            and boton.get_attribute("aria-disabled") != "true"
            and "button-disabled" not in clases.lower()
            and "deshabilitado" not in etiqueta.lower()
        )

    def _reiniciar_buscador_si_fallo_captcha(self, causa):
        if not self._captcha_reinicio_buscador_pendiente:
            return False
        logger.warning(
            "[CAPTCHA] Reiniciando el formulario antes de la siguiente causa."
        )
        self._reload_navegacion(
            "reiniciar_formulario_tras_fallo_captcha",
            wait_until="domcontentloaded",
            timeout=self.navegacion["retorno_buscador_timeout_ms"],
        )
        self._esperar_buscador_listo(causa)
        self._captcha_reinicio_buscador_pendiente = False
        return True

    def _escribir_causa_en_campo(self, campo, numero_juicio):
        """Escribe la causa de inmediato y conserva un respaldo para la máscara.

        ``press_sequentially`` simula un teclado físico y añade una espera por
        carácter. El formulario actual de e-SATJE acepta ``fill`` y recibe los
        eventos explícitos de Angular, por lo que el valor aparece de una sola
        vez. Si una versión futura de la máscara no lo conserva, se usa la
        escritura secuencial como respaldo antes de declarar el fallo.
        """
        causa = self._causa_canonica(numero_juicio)
        valor_formulario = self._causa_para_formulario(numero_juicio)

        campo.fill("")
        campo.fill(valor_formulario)
        campo.dispatch_event("input")
        campo.dispatch_event("change")
        if self._causa_canonica(campo.input_value()) == causa:
            return "fill"

        logger.warning(
            "[NAVEGACION_ESATJE] La máscara no conservó la escritura directa; "
            "se aplica respaldo secuencial para %s.",
            causa,
        )
        campo.fill("")
        campo.press_sequentially(valor_formulario, delay=0)
        campo.dispatch_event("input")
        campo.dispatch_event("change")
        if self._causa_canonica(campo.input_value()) != causa:
            raise RuntimeError("CAUSA_NO_CONFIRMADA_EN_CAMPO")
        return "secuencial_respaldo"

    def _preparar_busqueda(self, numero_juicio):
        causa = self._causa_canonica(numero_juicio)
        if not causa:
            raise ValueError("CAUSA_VACIA")

        if not self.regresar_al_buscador():
            raise RuntimeError("NO_SE_PUDO_VOLVER_AL_BUSCADOR")
        self._reiniciar_buscador_si_fallo_captcha(causa)

        campo = self._input_causa_unico()
        self._escribir_causa_en_campo(campo, numero_juicio)

        self._cambiar_estado_navegacion(causa, "PREPARAR_BUSCADOR", "CAUSA_ESCRITA", "escribir_causa")
        return causa

    def _esperar_busqueda_habilitada(
        self, causa, timeout_ms=None, accion_timeout="espera_pasiva_timeout",
        codigo_timeout="CAPTCHA_TIMEOUT",
    ):
        espera_ms = (
            self.navegacion["captcha_timeout_ms"]
            if timeout_ms is None else max(0, int(timeout_ms))
        )
        limite = monotonic() + (espera_ms / 1000)
        limite_renderizado = min(
            limite,
            monotonic() + (self.navegacion.get("captcha_render_timeout_ms", 15000) / 1000),
        )
        estable = 0
        captcha_renderizado = False
        causa_reescrita = False
        estado_espera = self.ultimo_estado_navegacion or "CAPTCHA_SOLICITADO"
        while monotonic() < limite:
            campo = self._input_causa_unico()
            boton = self._boton_buscar_unico()
            causa_correcta = self._causa_canonica(campo.input_value()) == causa
            habilitado = self._boton_habilitado(boton)
            captcha_renderizado = captcha_renderizado or self._captcha_renderizado()
            esperando_renderizado = not captcha_renderizado and monotonic() < limite_renderizado

            if captcha_renderizado and habilitado and not causa_correcta and not causa_reescrita:
                self._escribir_causa_en_campo(campo, causa)
                causa_reescrita = True
                self.page.wait_for_timeout(250)
                continue

            if not esperando_renderizado and causa_correcta and habilitado:
                estable += 1
                if estable >= 2:
                    self._cambiar_estado_navegacion(
                        causa, estado_espera, "BUSQUEDA_HABILITADA",
                        "captcha_finalizado",
                    )
                    return boton
            else:
                estable = 0
            self.page.wait_for_timeout(250)

        self._captcha_reinicio_buscador_pendiente = True
        self._cambiar_estado_navegacion(
            causa, estado_espera, "CAPTCHA_TIMEOUT", accion_timeout,
            timeout_ms=espera_ms,
        )
        raise PlaywrightTimeoutError(
            "%s: BUSCAR no quedo habilitado" % codigo_timeout
        )

    def _enviar_busqueda_una_vez(self, causa, intento_id):
        clave = (causa, intento_id)
        if clave in self._busquedas_enviadas:
            raise RuntimeError("DOBLE_CLICK_BUSCAR_BLOQUEADO")

        campo = self._input_causa_unico()
        boton = self._boton_buscar_unico()
        if self._causa_canonica(campo.input_value()) != causa:
            raise RuntimeError("CAUSA_CAMBIO_ANTES_DE_BUSCAR")
        if not self._boton_habilitado(boton):
            raise RuntimeError("BUSCAR_NO_HABILITADO")

        self._busquedas_enviadas.add(clave)
        boton.click()
        self._cambiar_estado_navegacion(
            causa,
            "BUSQUEDA_HABILITADA",
            "BUSQUEDA_ENVIADA",
            "click_buscar",
            intento_id=intento_id,
            click_numero=1,
        )

    def _filas_resultado_coincidentes(self, causa):
        causa = self._causa_canonica(causa)
        filas = self.page.locator(
            "section.causas .cuerpo .causa-individual, "
            ".cuerpo .causa-individual, table tbody tr, table tr, mat-row, "
            "[role='grid'] [role='row'], [role='row']"
        )
        coincidencias = []
        for indice in range(filas.count()):
            fila = filas.nth(indice)
            try:
                if fila.is_visible() and self._fila_corresponde_causa(fila, causa):
                    coincidencias.append(fila)
            except Exception:
                continue
        return coincidencias

    def _esperar_resultados(self, causa):
        limite = monotonic() + (self.navegacion["resultados_timeout_ms"] / 1000)
        while monotonic() < limite:
            texto = self.page.inner_text("body")
            texto_normalizado = re.sub(r"\s+", " ", texto).strip().upper()
            if re.search(
                r"\bLA CONSULTA NO DEVOLVI(?:O|\u00D3) RESULTADOS\b",
                texto_normalizado,
            ):
                self._cambiar_estado_navegacion(
                    causa,
                    "BUSQUEDA_ENVIADA",
                    "VERIFICACION_MANUAL",
                    "notificacion_sin_resultados",
                )
                return "VERIFICACION_MANUAL_SIN_RESULTADOS"
            if self._motivo_rechazo_formulario(texto_normalizado):
                self._cambiar_estado_navegacion(
                    causa, "BUSQUEDA_ENVIADA", "BUSQUEDA_RECHAZADA",
                    "validar_rechazo_formulario",
                )
                raise RuntimeError("BUSQUEDA_RECHAZADA_FORMULARIO")
            if re.search(r"REGISTROS\s+ENCONTRADOS\s*:\s*0", texto_normalizado) or (
                "NO SE ENCONTRARON RESULTADOS" in texto_normalizado
            ):
                self._cambiar_estado_navegacion(causa, "BUSQUEDA_ENVIADA", "SIN_RESULTADOS", "validar_resultados")
                return "SIN_RESULTADOS"

            coincidencias = self._filas_resultado_coincidentes(causa)
            if len(coincidencias) == 1:
                self._cambiar_estado_navegacion(causa, "BUSQUEDA_ENVIADA", "RESULTADOS_LISTOS", "validar_resultados")
                return coincidencias[0]
            if len(coincidencias) > 1:
                self._cambiar_estado_navegacion(causa, "BUSQUEDA_ENVIADA", "RESULTADO_AMBIGUO", "validar_resultados")
                raise RuntimeError("RESULTADO_AMBIGUO")
            self.page.wait_for_timeout(250)

        raise PlaywrightTimeoutError("RESULTADOS_TIMEOUT")

    @staticmethod
    def _motivo_rechazo_formulario(texto):
        """Reconoce rechazos explícitos de Angular después de pulsar BUSCAR."""
        texto = re.sub(r"\s+", " ", str(texto or "")).strip().upper()
        if "EL FORMULARIO CONTIENE ERRORES" in texto or "REVISE LOS CAMPOS MARCADOS" in texto:
            return "FORMULARIO_CONTIENE_ERRORES"
        return None

    def _boton_carpeta_en_fila(self, fila, contexto):
        selectores = (
            "button:has(i.fa-folder), a:has(i.fa-folder), button:has(i.fa-folder-open), a:has(i.fa-folder-open)",
            "[role='link']:has(i.material-icons:has-text('folder')), [role='link']:has(i:has-text('folder'))",
            "button[aria-label*='detalle' i], a[aria-label*='detalle' i], [role='link'][aria-label*='detalle' i]",
            "[mattooltip='Ver archivos'], [role='link'][aria-label*='archivo' i]",
        )
        for selector in selectores:
            botones = fila.locator(selector)
            if botones.count() == 1:
                return botones.nth(0)

        accionables = fila.locator("button, a, [role='link'], [role='button'], [mattooltip='Ver archivos']")
        candidatos = []
        for indice in range(accionables.count()):
            accionable = accionables.nth(indice)
            try:
                etiqueta = " ".join(
                    filtro for filtro in (
                        accionable.get_attribute("aria-label"),
                        accionable.get_attribute("title"),
                        accionable.inner_text(),
                    ) if filtro
                ).upper()
                tiene_icono = accionable.locator(
                    "i.fa-folder, i.fa-folder-open, i.material-icons:has-text('folder'), i:has-text('folder')"
                ).count() > 0
                if "CARPETA" in etiqueta or "ARCHIVO" in etiqueta or tiene_icono:
                    candidatos.append(accionable)
            except Exception:
                continue
        if len(candidatos) != 1:
            raise RuntimeError(f"CARPETA_AMBIGUA_O_AUSENTE:{contexto}")
        return candidatos[0]

    def _abrir_detalle_causa(self, causa, fila):
        causa = self._causa_canonica(causa)
        if not self._fila_corresponde_causa(fila, causa):
            raise RuntimeError("FILA_NO_CORRESPONDE_A_CAUSA")

        if "/causas" in self.page.url.lower():
            enlace_movimientos = fila.locator(
                "a[aria-label*='movimientos' i], a:has(mat-icon:has-text('folder_open'))"
            )
            if enlace_movimientos.count() != 1:
                raise RuntimeError("ENLACE_MOVIMIENTOS_FILA_AUSENTE_O_AMBIGUO")
            etiqueta = enlace_movimientos.first.get_attribute("aria-label") or ""
            if not self._texto_contiene_causa_numerica_exacta(etiqueta, causa):
                raise RuntimeError("ENLACE_MOVIMIENTOS_NO_CORRESPONDE_A_CAUSA")
            enlace_movimientos.first.scroll_into_view_if_needed()
            if not enlace_movimientos.first.is_visible() or not enlace_movimientos.first.is_enabled():
                raise RuntimeError("ENLACE_MOVIMIENTOS_NO_ACCIONABLE")
            enlace_movimientos.first.click()
            self.page.wait_for_url(
                re.compile(r"/movimientos(?:[/?#]|$)"),
                timeout=self.navegacion["datos_generales_timeout_ms"],
            )
            enlace_detalle = self.page.locator(
                "[mattooltip='Ver detalle del proceso judicial'], "
                "[aria-label*='detalle del proceso judicial' i]"
            )
            if enlace_detalle.count() != 1:
                raise RuntimeError("ENLACE_DETALLE_PROCESO_AUSENTE_O_AMBIGUO")
            enlace_detalle.first.click()
            self.page.wait_for_url(
                re.compile(r"/actuaciones(?:[/?#]|$)"),
                timeout=self.navegacion["datos_generales_timeout_ms"],
            )
            self._cambiar_estado_navegacion(
                causa, "RESULTADOS_LISTOS", "DETALLE_CAUSA_ABIERTO", "click_movimientos_y_detalle"
            )
            return
        carpeta = self._boton_carpeta_en_fila(fila, "detalle")
        carpeta.scroll_into_view_if_needed()
        if not carpeta.is_visible() or not carpeta.is_enabled():
            raise RuntimeError("CARPETA_DETALLE_NO_ACCIONABLE")
        carpeta.click()
        self._cambiar_estado_navegacion(causa, "RESULTADOS_LISTOS", "DETALLE_CAUSA_ABIERTO", "click_carpeta_detalle")

    def _esperar_datos_generales(self, causa):
        limite = monotonic() + (self.navegacion["datos_generales_timeout_ms"] / 1000)
        while monotonic() < limite:
            texto = self.page.inner_text("body")
            texto_normalizado = texto.upper()
            if (
                "DATOS GENERALES" in texto_normalizado
                and "NUMERO DE PROCESO" in texto_normalizado
                and self._texto_contiene_causa_numerica_exacta(texto, causa)
            ):
                self._cambiar_estado_navegacion(causa, "DETALLE_CAUSA_ABIERTO", "DATOS_GENERALES_LISTOS", "validar_datos_generales")
                return True
            self.page.wait_for_timeout(250)
        raise PlaywrightTimeoutError("DATOS_GENERALES_TIMEOUT")

    def _esperar_pantalla_final_estable(self, causa):
        """Espera a que terminen de renderizar actuaciones y controles de archivos."""
        limite = monotonic() + (self.navegacion["pantalla_final_timeout_ms"] / 1000)
        firma_anterior = None
        estable = 0
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        while monotonic() < limite:
            texto = self.page.inner_text("body")
            carpetas = self.page.locator(
                "[mattooltip='Ver archivos'], [role='link'][aria-label*='archivos' i]"
            )
            firma = (len(texto), carpetas.count(), self.page.locator(".fila").count())
            if "INFORMACION DEL PROCESO" in texto.upper() and carpetas.count() > 0 and firma == firma_anterior:
                estable += 1
                if estable >= 3:
                    self.page.wait_for_timeout(self.navegacion["pantalla_final_estabilizacion_ms"])
                    self._cambiar_estado_navegacion(
                        causa, "DATOS_GENERALES_LISTOS", "PANTALLA_FINAL_ESTABLE", "estabilizar_actuaciones"
                    )
                    return True
            else:
                estable = 0
            firma_anterior = firma
            self.page.wait_for_timeout(250)
        raise PlaywrightTimeoutError("PANTALLA_FINAL_NO_ESTABLE")

    def _descriptores_carpetas_actuaciones(self):
        filas = self.page.locator("table tbody tr, table tr, [role='row'], mat-row, .fila")
        descriptores = []
        vistos = set()
        for indice in range(filas.count()):
            fila = filas.nth(indice)
            try:
                if not fila.is_visible():
                    continue
                texto = " ".join(fila.inner_text().split())
                if not texto:
                    continue
                carpeta = self._boton_carpeta_en_fila(fila, "actuaciones")
                if not carpeta.is_visible():
                    continue
                clave = re.sub(r"\s+", " ", texto.upper())[:300]
                if clave not in vistos:
                    vistos.add(clave)
                    descriptores.append({"clave": clave, "indice_visual": indice, "texto": texto})
            except RuntimeError:
                continue
        return descriptores

    def _localizar_fila_carpeta(self, descriptor):
        filas = self.page.locator("table tbody tr, table tr, [role='row'], mat-row, .fila")
        candidatos = []
        for indice in range(filas.count()):
            fila = filas.nth(indice)
            try:
                texto = re.sub(r"\s+", " ", fila.inner_text().upper())[:300]
                if fila.is_visible() and texto == descriptor["clave"]:
                    candidatos.append(fila)
            except Exception:
                continue
        if len(candidatos) != 1:
            raise RuntimeError("CARPETA_NO_RELOCALIZABLE")
        return candidatos[0]

    def _esperar_actuaciones(self, causa):
        limite = monotonic() + (self.navegacion["actuaciones_timeout_ms"] / 1000)
        senales = ("INFORMACION DEL PROCESO", "EXPORTAR PDF", "AMPLIAR TODO", "CONTRAER TODO")
        while monotonic() < limite:
            texto = self.page.inner_text("body").upper()
            if any(senal in texto for senal in senales):
                self._cambiar_estado_navegacion(causa, "ABRIR_CARPETA", "ACTUACIONES_LISTAS", "validar_actuaciones")
                return True
            self.page.wait_for_timeout(250)
        raise PlaywrightTimeoutError("ACTUACIONES_TIMEOUT")

    def _volver_a_datos_generales(self, causa):
        for nombre in ("Cerrar", "Regresar"):
            boton = self.page.get_by_role("button", name=re.compile(rf"^\s*{nombre}\s*$", re.IGNORECASE))
            if boton.count() == 1:
                boton.nth(0).click()
                try:
                    self._esperar_datos_generales(causa)
                    return True
                except PlaywrightTimeoutError:
                    continue
        try:
            self.page.go_back()
            self._esperar_datos_generales(causa)
            return True
        except Exception:
            return False

    def _volver_al_buscador(self, causa):
        """Regresa al formulario y verifica que el ?nico campo de causa est? disponible."""
        for _ in range(3):
            try:
                campo = self._input_causa_unico()
                if campo.is_visible():
                    self._cambiar_estado_navegacion(
                        causa, "VOLVER_AL_BUSCADOR", "BUSCADOR_LISTO", "validar_formulario"
                    )
                    return True
            except RuntimeError:
                pass

            boton = self.page.get_by_role(
                "button", name=re.compile(r"^\s*Regresar\s*$", re.IGNORECASE)
            )
            if boton.count() == 1 and boton.nth(0).is_visible():
                boton.nth(0).click()
            else:
                try:
                    self.page.go_back()
                except Exception:
                    break
            self.page.wait_for_timeout(250)

        raise RuntimeError("NO_SE_PUDO_VOLVER_AL_BUSCADOR")

    @staticmethod
    def _clave_archivo(valor):
        return re.sub(r"[^A-Za-z0-9_-]+", "_", str(valor or "")).strip("_")[:80] or "sin_clave"

    def _guardar_evidencia_fallo(self, causa, estado, error, carpeta=None):
        """Guarda evidencia diagn?stica sin interrumpir el tratamiento del error."""
        try:
            directorio = os.path.join("data", "temp_htmls")
            os.makedirs(directorio, exist_ok=True)
            sufijo = "_".join(
                self._clave_archivo(valor)
                for valor in (self._causa_canonica(causa), estado, carpeta)
                if valor
            )
            base = os.path.join(directorio, sufijo)
            if self.page and not self.page.is_closed():
                try:
                    self.page.screenshot(path=f"{base}.png", full_page=True)
                except Exception:
                    pass
                try:
                    with open(f"{base}.html", "w", encoding="utf-8") as archivo:
                        archivo.write(self.page.content())
                except Exception:
                    pass
                url = self.page.url
            else:
                url = None

            evidencia = {
                "causa": self._causa_canonica(causa),
                "estado": estado,
                "carpeta": carpeta,
                "url": url,
                "error": str(error),
                "traza": format_exc(),
                "ultimo_paquete_api": self.paquetes_api_interceptados[-1] if self.paquetes_api_interceptados else None,
            }
            with open(f"{base}.json", "w", encoding="utf-8") as archivo:
                json.dump(evidencia, archivo, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            logger.warning("[NAVEGACION_ESATJE] No se pudo guardar evidencia: %s", exc)

    def _paquetes_api_de_carpeta(self, paquetes, causa):
        """A?sla paquetes posteriores al clic de carpeta y descarta respuestas no relacionadas."""
        causa = self._causa_canonica(causa)
        seleccionados = []
        for paquete in paquetes:
            url = str(paquete.get("url", "")).lower()
            contenido = json.dumps(paquete.get("data", ""), ensure_ascii=False, default=str)
            contenido_canonico = self._causa_canonica(contenido)
            es_actuacion = "actuacion" in url
            contiene_causa = causa and causa in contenido_canonico
            contiene_otro_identificador = bool(re.search(r"\d{10,}", contenido))
            if es_actuacion and (contiene_causa or not contiene_otro_identificador):
                seleccionados.append(paquete)
        return seleccionados

    def _metadatos_carpeta(self, causa, descriptor):
        texto = re.sub(r"\s+", " ", descriptor.get("texto", "")).strip()
        dependencia = re.search(
            r"DEPENDENCIA JURISDICCIONAL\s*:\s*(.*?)(?=\s+CIUDAD\s*:|$)",
            texto,
            re.IGNORECASE,
        )
        ciudad = re.search(r"CIUDAD\s*:\s*(.*?)(?=\s+\d{1,3}\s+\d{2}/\d{2}/\d{4}|$)", texto, re.IGNORECASE)
        return {
            "CAUSA": self._causa_canonica(causa),
            "CLAVE_CARPETA": descriptor["clave"],
            "INSTANCIA_CARPETA": descriptor.get("indice_visual"),
            "DEPENDENCIA_JURISDICCIONAL": dependencia.group(1).strip() if dependencia else None,
            "CIUDAD_CARPETA": ciudad.group(1).strip() if ciudad else None,
        }

    def _aplicar_inferencia_consolidada(
        self, datos, causa=None, demandados=None, alcance="carpeta"
    ):
        """Aplica y deja trazada la inferencia definitiva del alcance indicado."""
        actuaciones = datos.get("HISTORIAL_ACTUACIONES", [])
        if not actuaciones:
            return datos

        from src.agente_extractor import MotorInferenciaProcesal
        inferencia = MotorInferenciaProcesal.inferir_estado_procesal(
            actuaciones, causa=causa, demandados=demandados
        )
        if not inferencia or not inferencia.get("ULTIMA_ETAPA"):
            return datos

        etapa_operativa = inferencia.get("ETAPA_ACTUAL") or inferencia.get("ULTIMA_ETAPA")
        fase_operativa = inferencia.get("FASE_ACTUAL") or inferencia.get("ULTIMA_FASE")
        datos["ETAPA_PROCESAL"] = etapa_operativa
        datos["FASE_PROCESAL"] = fase_operativa
        datos["FECHA INICIAL FASE ACTUAL"] = inferencia.get("FECHA_INICIO_FASE_ACTUAL")
        datos["ULTIMA ETAPA"] = inferencia.get("ULTIMA_ETAPA")
        datos["ULTIMA FASE"] = inferencia.get("ULTIMA_FASE")
        datos["FECHA FIN ULTIMA FASE"] = inferencia.get("FECHA_FIN_ULTIMA_FASE")
        datos["ETAPA ACTUAL"] = etapa_operativa
        datos["FASE ACTUAL"] = fase_operativa
        datos["FECHA INICIO FASE ACTUAL"] = inferencia.get("FECHA_INICIO_FASE_ACTUAL")
        enriquecer_datos_procesales(datos)
        if inferencia.get("MENSAJE_ESPECIAL"):
            datos["COMENTARIO_ULTIMO"] = inferencia.get("MENSAJE_ESPECIAL")
        try:
            log_payload = {
                "source": datos.get("ORIGEN_DATA") or "consolidado",
                "reason": "inferencia_consolidada",
                "estado_decision": "FINAL",
                "alcance": alcance,
                "causa": self._causa_canonica(causa) if causa else None,
                "fase_deducida": datos["ULTIMA FASE"],
                "etapa": datos["ULTIMA ETAPA"],
                "fecha_final": datos["FECHA FIN ULTIMA FASE"],
                "fase_actual": inferencia.get("FASE_ACTUAL"),
                "actuacion_respaldo": str(
                    inferencia.get("ACTUACION_RESPALDO") or ""
                )[:500],
                "actuacion_pendiente_revision": inferencia.get(
                    "ACTUACION_PENDIENTE_REVISION"
                ),
                "regla_aplicada": inferencia.get("REGLA_APLICADA"),
                "num_actuaciones": len(actuaciones),
            }
            logger.info("[DECISION_FASE_FINAL] %s", json.dumps(log_payload, ensure_ascii=False))
        except Exception:
            logger.warning("No se pudo registrar la decision final de fase.", exc_info=True)
        return datos

    def _procesar_todas_las_carpetas(self, causa):
        descriptores = self._descriptores_carpetas_actuaciones()
        if not descriptores:
            raise RuntimeError("SIN_CARPETAS_ACTUACIONES")

        resultados = []
        errores = []
        for descriptor in descriptores:
            try:
                fila = self._localizar_fila_carpeta(descriptor)
                carpeta = self._boton_carpeta_en_fila(fila, "actuaciones")
                cursor_api = len(self.paquetes_api_interceptados)
                carpeta.scroll_into_view_if_needed()
                carpeta.click()
                self._cambiar_estado_navegacion(causa, "DATOS_GENERALES_LISTOS", "ABRIR_CARPETA", "click_carpeta_actuaciones", carpeta=descriptor["clave"])
                self._esperar_actuaciones(causa)
                paquetes_carpeta = self._paquetes_api_de_carpeta(
                    self.paquetes_api_interceptados[cursor_api:], causa
                )
                datos = self._ejecutar_extraccion_detalles(
                    causa, paquetes_api=paquetes_carpeta, carpeta=descriptor["clave"]
                )
                if isinstance(datos, dict):
                    datos["ORIGEN_CARPETA"] = descriptor
                    datos["ORIGEN_DATA"] = "API" if paquetes_carpeta else "DOM"
                    datos.setdefault("HISTORIAL_ACTUACIONES", [])
                    resultados.append(datos)
                if not self._volver_a_datos_generales(causa):
                    raise RuntimeError("NO_SE_PUDO_VOLVER_A_DATOS_GENERALES")
            except Exception as exc:
                errores.append({"carpeta": descriptor, "error": str(exc)})
                logger.warning("[NAVEGACION_ESATJE] Carpeta parcial %s: %s", descriptor["clave"], exc)
                self._guardar_evidencia_fallo(causa, "ERROR_CARPETA", exc, descriptor["clave"])
                self._volver_a_datos_generales(causa)

        if not resultados:
            raise RuntimeError("CARPETAS_SIN_EXTRACCION")

        consolidado = dict(resultados[0])
        actuaciones = []
        vistas = set()
        for datos in resultados:
            for actuacion in datos.get("HISTORIAL_ACTUACIONES", []):
                enriquecida = dict(actuacion)
                enriquecida.update(self._metadatos_carpeta(causa, datos["ORIGEN_CARPETA"]))
                enriquecida["ORIGEN_CARPETA"] = datos["ORIGEN_CARPETA"]["clave"]
                enriquecida["ORIGEN_DATA"] = datos.get("ORIGEN_DATA")
                clave = (
                    enriquecida.get("fecha"),
                    enriquecida.get("detalle"),
                    enriquecida["ORIGEN_CARPETA"],
                )
                if clave not in vistas:
                    vistas.add(clave)
                    actuaciones.append(enriquecida)
        consolidado["HISTORIAL_ACTUACIONES"] = actuaciones
        consolidado["CARPETAS_PROCESADAS"] = [d["ORIGEN_CARPETA"] for d in resultados]
        consolidado["ERRORES_CARPETAS"] = errores
        consolidado["ESTADO_NAVEGACION"] = "PARCIAL" if errores else "COMPLETADO"
        self._aplicar_inferencia_consolidada(
            consolidado, causa=causa, alcance="causa"
        )
        return consolidado

    def _procesar_flujo_autonomo(self, numero_juicio):
        causa_original = str(numero_juicio or "").strip()
        causa = self._causa_canonica(causa_original)
        self.paquetes_api_interceptados.clear()
        self._busquedas_enviadas.clear()
        max_intentos = int(self.navegacion["max_reintentos_transicion"])

        for intento in range(1, max_intentos + 1):
            intento_id = f"{causa}:{intento}"
            try:
                if not self._verificar_sesion_activa():
                    raise RuntimeError("SESION_EXPIRADA")
                causa = self._preparar_busqueda(causa_original)
                self._cambiar_estado_navegacion(causa, "CAUSA_ESCRITA", "ESPERAR_FIN_CAPTCHA", "esperar_buscar_habilitado")
                self._esperar_busqueda_habilitada(causa)
                self._enviar_busqueda_una_vez(causa, intento_id)
                resultado = self._esperar_resultados(causa)
                if resultado == "SIN_RESULTADOS":
                    self.datos_extraidos = {"ESTADO_NAVEGACION": "SIN_RESULTADOS", "HISTORIAL_ACTUACIONES": []}
                    return False

                self._abrir_detalle_causa(causa, resultado)
                self._esperar_datos_generales(causa)
                self._esperar_pantalla_final_estable(causa)
                self.datos_extraidos = self._procesar_todas_las_carpetas(causa)
                self._volver_a_datos_generales(causa)
                self._volver_al_buscador(causa)
                self._cambiar_estado_navegacion(causa, "CONSOLIDAR_EVIDENCIA", "CAUSA_COMPLETADA", "volver_al_buscador")
                return True
            except PlaywrightTimeoutError as exc:
                estado = self.ultimo_estado_navegacion or "CAPTCHA_TIMEOUT"
                self._cambiar_estado_navegacion(causa, estado, "ERROR_NAVEGACION", "timeout", error=str(exc), intento=intento)
                self._guardar_evidencia_fallo(causa, estado, exc)
            except Exception as exc:
                estado = self.ultimo_estado_navegacion or "ERROR_NAVEGACION"
                self._cambiar_estado_navegacion(causa, estado, "ERROR_NAVEGACION", "error", error=str(exc), intento=intento)
                self._guardar_evidencia_fallo(causa, estado, exc)

            if intento < max_intentos:
                try:
                    self._volver_al_buscador(causa)
                except Exception as retorno_error:
                    logger.warning("[NAVEGACION_ESATJE] No se pudo reiniciar el formulario: %s", retorno_error)

        self.datos_extraidos = {
            "ESTADO_NAVEGACION": "ERROR_NAVEGACION",
            "HISTORIAL_ACTUACIONES": [],
        }
        return False

    def procesar_flujo_judicatura(self, numero_juicio):
        """
        Modo Híbrido Asistido con Arquitectura de Ejecución Dual:
        1. Prepara búsqueda en Nivel 0.
        2. Aplica freno de ejecución estricto: wait_for_selector('text="Actor/Ofendido:"', state='visible').
        3. Procesa Ruta Principal (API + Pandas) o Ruta Respaldo (BeautifulSoup4 + DOM).
        """
        logger.info("Iniciando causa: %s", numero_juicio)
        return self._procesar_flujo_autonomo(numero_juicio)
        self.paquetes_api_interceptados.clear()
        
        # Freno de ejecución estricto: debe coincidir ÚNICAMENTE con la vista de detalle del expediente (Image 2),
        # NO con la cabecera de la tabla de judicaturas "Actuaciones Judiciales" (Image 1).
        selector_freno_estricto = "text=/Información del proceso|Exportar PDF|Ampliar todo|Contraer todo/i"
        max_reintentos = 3
        intentos = 0

        while intentos < max_reintentos:
            try:
                # 0. Verificar sesión activa antes de cada intento
                self._verificar_sesion_activa()

                # 1. Preparar entrada en caja de búsqueda (Nivel 0)
                try:
                    input_causa = self.page.locator("input[placeholder*='códigoDependencia-Año-Secuencial']").first
                    if not input_causa.is_visible():
                        self.regresar_al_buscador()

                    if input_causa.is_visible():
                        input_causa.fill("")
                        input_causa.fill(str(numero_juicio).strip())
                        logger.info("Causa '%s' lista en el buscador.", numero_juicio)
                        logger.info("Por favor, resuelve Captcha / busca y navega a la carpeta del expediente...")
                except Exception as e_fill:
                    logger.warning("Aviso al preparar la caja de búsqueda: %s", e_fill)

                # Intentar auto-click en el icono de carpeta 📁 si estamos en la tabla de resultados (Image 1)
                try:
                    self.page.wait_for_timeout(1000)
                    if not self.page.locator(selector_freno_estricto).first.is_visible():
                        for btn_sel in [
                            "tr td button:has(i)",
                            "tr td button",
                            "tr td a",
                            "i.fa-folder",
                            "i.fa-folder-open",
                            "button:has(.fa-folder)",
                        ]:
                            try:
                                folder_btn = self.page.locator(btn_sel).first
                                if folder_btn.is_visible():
                                    logger.info("Navegando automáticamente al expediente (click en carpeta 📁)...")
                                    folder_btn.click()
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass

                # 2. RUTA RESPALDO: Freno de Ejecución Estricto en la pantalla de detalle del expediente (Image 2)
                logger.info("FRENO DE EJECUCIÓN: Aguardando apertura del expediente (vista de detalle 'Información del proceso')...")
                self.page.wait_for_selector(selector_freno_estricto, state="visible", timeout=300000)
                self.nav_arbol.bajar_nivel("Expediente abierto -> Profundizando en contenido")

                # 3. Procesamiento Dual (API Fetching + Pandas // DOM + BS4)
                self.datos_extraidos = self._ejecutar_extraccion_detalles(numero_juicio)

                # 4. Esperar a que el usuario cierre el expediente (retorno en árbol)
                logger.info("Aguardando a que el operador cierre el expediente (state: hidden)...")
                self.page.wait_for_selector(selector_freno_estricto, state="hidden", timeout=300000)
                self.nav_arbol.subir_nivel("Expediente cerrado -> Retornando al nivel superior")

                return True

            except PlaywrightTimeoutError:
                intentos += 1
                logger.warning("Timeout alcanzado (intento %s/%s). El selector no apareció en 5 minutos.", intentos, max_reintentos)
                if intentos >= max_reintentos:
                    logger.error("Máximo de reintentos alcanzado para causa %s. Abortando.", numero_juicio)
                    return False
            except Exception as e:
                intentos += 1
                msg_err = str(e).lower()
                logger.warning("Excepción en bucle de observación pasiva (intento %s/%s): %s", intentos, max_reintentos, e)
                if "closed" in msg_err or "target page" in msg_err:
                    logger.warning("[!] Detectado cierre de navegador. Relanzando Chromium automáticamente...")
                    self.asegurar_navegador_vivo(modo_visible=True)
                if intentos >= max_reintentos:
                    logger.error("Máximo de reintentos alcanzado para causa %s. Abortando.", numero_juicio)
                    return False
                try:
                    if self.page and not self.page.is_closed():
                        self.page.wait_for_selector("body", state="visible", timeout=5000)
                except Exception:
                    pass

        return False

    def extraer_detalles_juicio(self):
        """Devuelve los datos procesados en la vista actual."""
        if self.datos_extraidos is not None:
            res = self.datos_extraidos
            self.datos_extraidos = None
            return res
        return self._ejecutar_extraccion_detalles()

    def _ejecutar_extraccion_detalles(self, numero_juicio=None, paquetes_api=None, carpeta=None):
        """
        Arquitectura Dual:
        - RUTA PRINCIPAL: Si la API interceptó JSON, procesar vectorialmente con Pandas (Bypass BeautifulSoup4).
        - RUTA RESPALDO: Si no hay API JSON, capturar HTML post-sincronización y procesar con BeautifulSoup4.
        Además, guarda artefactos (HTML + paquetes API) en data/temp_htmls para análisis cuando se pase numero_juicio.
        """
        datos = {
            "FECHA INICIO JUICIO": None,
            "FECHA INICIAL FASE ACTUAL": None,
            "ETAPA_PROCESAL": None,
            "FASE_PROCESAL": None
        }

        # --- RUTA PRINCIPAL: INTERCEPCIÓN API (BYPASS BEAUTIFULSOUP4 + PANDAS) ---
        paquetes = self.paquetes_api_interceptados if paquetes_api is None else paquetes_api

        if paquetes:
            # Cargar keywords configurables para detección de mandamiento (opcional)
            try:
                keywords = _load_extraction_keywords()
            except Exception:
                keywords = ['mandam','mandamiento','mandamiento de ejecucion','auto de ejecucion','auto de cumplimiento']

            logger.info("[RUTA PRINCIPAL API] Procesando %s respuesta(s) JSON con Pandas...", len(paquetes))
            try:
                registros = []
                for p in paquetes:
                    d = p.get("data")
                    if isinstance(d, dict):
                        registros.append(d)
                    elif isinstance(d, list):
                        registros.extend([item for item in d if isinstance(item, dict)])
                
                if registros:
                    df = pd.json_normalize(registros)
                    # Extracción vectorizada de fechas
                    cols_fechas = [c for c in df.columns if any(k in c.lower() for k in ["fechainicio", "fechaingreso", "fechaprovidencia", "fechapresentacion"]) ]
                    if cols_fechas:
                        primera_fecha = df[cols_fechas[0]].first_valid_index()
                        if primera_fecha is not None:
                            datos["FECHA INICIO JUICIO"] = str(df.at[primera_fecha, cols_fechas[0]])

                    # Recolectar actuaciones estructuradas desde la API JSON para inferencia jerárquica (Regla del Árbol)
                    actuaciones_api = []
                    for reg in registros:
                        acts = reg.get("actuaciones") or reg.get("listaActuaciones") or []
                        if isinstance(acts, list):
                            for act in acts:
                                if isinstance(act, dict):
                                    f_act = next(
                                        (act.get(campo) for campo in (
                                            "fecha", "fechaActuacion", "fechaProvidencia",
                                            "fechaCrea", "fechaCreacion", "fechaRegistro", "fechaIngreso"
                                        ) if act.get(campo)),
                                        None
                                    )
                                    d_act = act.get("actuacion") or act.get("detalle") or act.get("tipoActuacion") or act.get("actividad")
                                    if d_act:
                                        actuaciones_api.append({
                                            "fecha": str(f_act) if f_act else None,
                                            "detalle": str(d_act).upper()
                                        })

                    if actuaciones_api:
                        datos["HISTORIAL_ACTUACIONES"] = actuaciones_api
                        from src.agente_extractor import MotorInferenciaProcesal
                        res_api = MotorInferenciaProcesal.inferir_estado_procesal(
                            actuaciones_api, causa=numero_juicio
                        )
                        if res_api and res_api.get("ULTIMA_ETAPA"):
                            etapa_api = res_api.get("ULTIMA_ETAPA")
                            fase_api = res_api.get("ULTIMA_FASE")
                            fecha_api = res_api.get("FECHA_FIN_ULTIMA_FASE")
                            fecha_fase_actual = res_api.get("FECHA_INICIO_FASE_ACTUAL")
                            
                            etapa_operativa = res_api.get("ETAPA_ACTUAL") or etapa_api
                            fase_operativa = res_api.get("FASE_ACTUAL") or fase_api
                            datos["ETAPA_PROCESAL"] = etapa_operativa
                            datos["FASE_PROCESAL"] = fase_operativa
                            datos["FECHA INICIAL FASE ACTUAL"] = fecha_fase_actual
                            datos["ULTIMA ETAPA"] = etapa_api
                            datos["ULTIMA FASE"] = fase_api
                            datos["FECHA FIN ULTIMA FASE"] = fecha_api
                            datos["ETAPA ACTUAL"] = etapa_operativa
                            datos["FASE ACTUAL"] = fase_operativa
                            datos["FECHA INICIO FASE ACTUAL"] = fecha_fase_actual
                            enriquecer_datos_procesales(datos)
                            if res_api.get("MENSAJE_ESPECIAL"):
                                datos["COMENTARIO_ULTIMO"] = res_api.get("MENSAJE_ESPECIAL")

                            logger.info("[RUTA PRINCIPAL API] Clasificación por Regla del Árbol: '%s' / '%s' en fecha %s", etapa_api, fase_api, datos["FECHA INICIAL FASE ACTUAL"])
                            return datos
            except Exception as e_pandas:
                logger.warning("Conmutando a Ruta de Respaldo por aviso en Pandas: %s", e_pandas)

        # --- RUTA RESPALDO: SINCRONIZACIÓN DOM (AGENTE EXTRACTOR) ---
        logger.info("[RUTA RESPALDO DOM] Procesando HTML renderizado post-sincronización con AgenteExtractor...")
        try:
            # Intentar asegurar que el listado de actuaciones se cargue (esperar XHR o forzar click en la pestaña)
            try:
                # Esperar por una respuesta JSON o una URL con 'actuacion' en el path (más tolerante)
                resp = self.page.wait_for_response(
                    lambda r: (r.headers and 'content-type' in r.headers and 'json' in r.headers.get('content-type','').lower() and r.status in [200,201])
                              or 'actuacion' in r.url.lower() or 'actuaciones' in r.url.lower(),
                    timeout=5000
                )
                try:
                    logger.info("[RUTA RESPALDO DOM] Interceptada respuesta de actuaciones/JSON: %s", resp.url)
                except Exception:
                    logger.info("[RUTA RESPALDO DOM] Interceptada respuesta de actuaciones/JSON (URL no disponible)")
            except Exception:
                # Intentar clickar en pestañas comunes que cargan actuaciones (varias alternativas)
                clicked = False
                for sel in ["text='Actuaciones Judiciales'", "text='Actuaciones'", "a:has-text('Actuaciones')", "button:has-text('Actuaciones Judiciales')", "button:has-text('Actuaciones')"]:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible():
                            loc.scroll_into_view_if_needed()
                            loc.click()
                            self.page.wait_for_load_state("networkidle", timeout=5000)
                            logger.info("[RUTA RESPALDO DOM] Click en selector para cargar actuaciones: %s", sel)
                            clicked = True
                            break
                    except Exception:
                        continue

                # Si no se pudo clickar con selectores estándar, intentar clickar por texto via JS (más robusto para Angular/custom tags)
                if not clicked:
                    try:
                        js_click = (
                            "(function(){var els = Array.from(document.querySelectorAll('button, a, span, div'));"
                            "var r=els.find(e=>/actuaciones?/i.test(e.innerText)); if(r){r.scrollIntoView(); r.click(); return true;} return false;})()"
                        )
                        rv = self.page.evaluate(js_click)
                        if rv:
                            logger.info("[RUTA RESPALDO DOM] Click por texto realizado vía evaluate()")
                            try:
                                self.page.wait_for_load_state("networkidle", timeout=4000)
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Esperar explícitamente a que Angular inyecte las filas de la tabla de actuaciones en el DOM
            try:
                self.page.wait_for_selector(
                    "table tr td, tr.mat-row, mat-row, .actuacion-item, tr:has(td)",
                    state="visible",
                    timeout=8000
                )
                logger.info("[RUTA RESPALDO DOM] Tabla de actuaciones detectada y visible en el DOM.")
            except Exception:
                logger.warning("[!] No se detectaron filas de tabla explícitas en 8s; procediendo con la lectura del DOM actual.")

            # Esperar estabilización de red
            try:
                self.page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            # Capturar contenido principal y el contenido de frames/iframes para analizarlos todos juntos
            contenido_html = self.page.content()
            try:
                frames_html = []
                for f in self.page.frames:
                    try:
                        # proteger contra frames None en entornos de test
                        if f is None:
                            continue
                        fc = f.content()
                        if fc:
                            frames_html.append(fc)
                    except Exception:
                        # algunos frames pueden fallar al leer si son cross-origin — ignorar
                        continue
            except Exception:
                frames_html = []

            # Concatenar contenido principal + frames para pasar al extractor como respaldo más completo
            contenido_total = contenido_html + "\n" + "\n\n".join(frames_html)

            # Guardar artefactos para análisis offline si se proporcionó numero_juicio
            try:
                import json as _json
                dir_temp = os.path.join("data", "temp_htmls")
                os.makedirs(dir_temp, exist_ok=True)
                if numero_juicio:
                    # Guardar HTML combinado (principal + frames)
                    ruta_html = os.path.join(dir_temp, f"{numero_juicio}.html")
                    with open(ruta_html, "w", encoding="utf-8") as fh:
                        fh.write(contenido_total)
                    logger.info("[ARTIFACT] HTML (principal+frames) guardado en: %s", ruta_html)

                    # Guardar frames por separado para diagnóstico
                    try:
                        for idx, fhtml in enumerate(frames_html):
                            ruta_f = os.path.join(dir_temp, f"{numero_juicio}_frame_{idx+1}.html")
                            with open(ruta_f, "w", encoding="utf-8") as ff:
                                ff.write(fhtml)
                        if frames_html:
                            logger.info("[ARTIFACT] %s frame(s) guardado(s) para: %s", len(frames_html), numero_juicio)
                    except Exception:
                        pass

                    if paquetes:
                        sufijo = f"_{self._clave_archivo(carpeta)}" if carpeta else ""
                        ruta_api = os.path.join(dir_temp, f"{numero_juicio}{sufijo}_api.json")
                        with open(ruta_api, "w", encoding="utf-8") as fa:
                            _json.dump(paquetes, fa, ensure_ascii=False, indent=2)
                        logger.info("[ARTIFACT] Paquetes API guardados en: %s", ruta_api)
            except Exception as e_save:
                logger.warning("No se pudo guardar artefactos para %s: %s", numero_juicio, e_save)

            # Pasar el HTML combinado al extractor para mayor cobertura (incluye iframes cuando fue posible leerlos)
            datos_dom = self.extractor.procesar_html_string(contenido_total)

            # Conservar fecha de inicio si fue extraída previamente
            if datos["FECHA INICIO JUICIO"] and not datos_dom.get("FECHA INICIO JUICIO"):
                datos_dom["FECHA INICIO JUICIO"] = datos["FECHA INICIO JUICIO"]
            return datos_dom
        except Exception as e:
            logger.error("Inconveniente al leer actuaciones en Ruta Respaldo: %s", e)
            return datos

    def cerrar_navegador(self):
        """Cierra la sesión del navegador."""
        if hasattr(self, 'context') and self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if getattr(self, 'browser', None):
            try:
                self.browser.close()
            except Exception:
                pass
        if getattr(self, 'playwright', None):
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        logger.info("Navegador cerrado.")


class BotJudicialTransaccional(BotJudicial):
    """Flujo e-SATJE con navegación bloqueada durante cada extracción."""

    ESTADOS_CARPETA_TERMINALES = {
        "COMPLETA", "PARCIAL_REGISTRADA", "ERROR_REGISTRADO"
    }
    TRANSICIONES_VALIDAS = {
        "PREPARAR_BUSCADOR": {"CAUSA_ESCRITA"},
        "CAUSA_ESCRITA": {"ESPERAR_FIN_CAPTCHA"},
        "ESPERAR_FIN_CAPTCHA": {"CAPTCHA_SOLICITADO", "CAPTCHA_TIMEOUT"},
        "CAPTCHA_SOLICITADO": {"BUSQUEDA_HABILITADA", "CAPTCHA_TIMEOUT"},
        "BUSQUEDA_HABILITADA": {"BUSQUEDA_ENVIADA"},
        "BUSQUEDA_ENVIADA": {
            "RESULTADOS_LISTOS", "SIN_RESULTADOS", "RESULTADO_AMBIGUO",
            "BUSQUEDA_RECHAZADA", "BUSQUEDA_TIMEOUT", "VERIFICACION_MANUAL",
        },
        "BUSQUEDA_RECHAZADA": {"PREPARAR_BUSCADOR"},
        "BUSQUEDA_TIMEOUT": {"PREPARAR_BUSCADOR"},
        "RESULTADOS_LISTOS": {"ABRIENDO_MOVIMIENTOS"},
        "ABRIENDO_MOVIMIENTOS": {"MOVIMIENTOS_CARGANDO"},
        "MOVIMIENTOS_CARGANDO": {"MOVIMIENTOS_LISTOS"},
        "MOVIMIENTOS_LISTOS": {
            "CARPETAS_DESCUBIERTAS", "ABRIENDO_INFORMACION_PROCESO",
            "CONSOLIDACION_EN_PROGRESO",
        },
        "CARPETAS_DESCUBIERTAS": {"ABRIENDO_INFORMACION_PROCESO"},
        "ABRIENDO_INFORMACION_PROCESO": {"INFORMACION_PROCESO_CARGANDO"},
        "INFORMACION_PROCESO_CARGANDO": {"INFORMACION_PROCESO_LISTA"},
        "INFORMACION_PROCESO_LISTA": {"NAVEGACION_BLOQUEADA"},
        "NAVEGACION_BLOQUEADA": {"EXTRACCION_EN_PROGRESO", "NAVEGACION_REANUDADA"},
        "EXTRACCION_EN_PROGRESO": {
            "EXTRACCION_COMPLETA", "EXTRACCION_PARCIAL_REGISTRADA",
            "EXTRACCION_ERROR_REGISTRADO",
        },
        "EXTRACCION_COMPLETA": {"NAVEGACION_REANUDADA"},
        "EXTRACCION_PARCIAL_REGISTRADA": {"NAVEGACION_REANUDADA"},
        "EXTRACCION_ERROR_REGISTRADO": {"NAVEGACION_REANUDADA"},
        "NAVEGACION_REANUDADA": {"RETORNANDO_A_MOVIMIENTOS"},
        "RETORNANDO_A_MOVIMIENTOS": {"MOVIMIENTOS_CARGANDO"},
        "CONSOLIDACION_EN_PROGRESO": {"RETORNANDO_AL_BUSCADOR"},
        "RETORNANDO_AL_BUSCADOR": {
            "CAUSA_COMPLETADA", "CAUSA_PARCIAL", "CAUSA_ERROR",
            "CAUSA_SIN_RESULTADOS", "CAUSA_EXCLUIDA",
        },
        "SIN_RESULTADOS": {"RETORNANDO_AL_BUSCADOR"},
        "VERIFICACION_MANUAL": {"RETORNANDO_AL_BUSCADOR"},
    }

    def __init__(self, url_portal, navegacion=None, captcha=None, proveedor_captcha=None):
        super().__init__(url_portal, navegacion, captcha, proveedor_captcha)
        defaults = {
            "retorno_buscador_timeout_ms": 15000,
            "movimientos_timeout_ms": 30000,
            "sondeo_estabilidad_ms": 250,
            "comprobaciones_estables": 3,
            "quietud_api_ms": 750,
        }
        for clave, valor in defaults.items():
            self.navegacion.setdefault(clave, valor)
        self._secuencia_api = 0
        self._ultima_respuesta_api_monotonic = 0.0
        self._bloqueo_navegacion = None
        self._intento_actual = None
        self._claves_extraidas = set()
        self._resultados_carpeta_actuales = []
        self._descriptores_actuales = []
        self._intentos_navegacion_bloqueados = []
        self._retorno_buscador_actual = None
        self._retorno_buscador_preparacion = None

    @staticmethod
    def _ahora_iso():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _ruta_es(url, ruta):
        from urllib.parse import urlparse
        try:
            return urlparse(str(url)).path.rstrip("/") == ruta.rstrip("/")
        except Exception:
            return False

    def _es_buscador(self):
        return any(self._ruta_es(self.page.url, ruta) for ruta in (
            "/busqueda-filtros", "/busqueda"
        ))

    def _cambiar_estado_navegacion(self, causa, anterior, siguiente, accion, **extra):
        estado_real = self.ultimo_estado_navegacion
        if estado_real is not None and anterior not in (None, estado_real):
            raise RuntimeError(
                f"TRANSICION_ORIGEN_INCONSISTENTE:{estado_real}->{siguiente}"
            )
        if (
            estado_real is not None
            and siguiente not in self.TRANSICIONES_VALIDAS.get(estado_real, set())
            and siguiente not in {"ERROR_NAVEGACION", "CAUSA_ERROR"}
        ):
            raise RuntimeError(f"TRANSICION_NO_PERMITIDA:{estado_real}->{siguiente}")
        self.ultimo_estado_navegacion = siguiente
        evento = {
            "causa": self._causa_canonica(causa),
            "estado_anterior": estado_real or anterior,
            "estado_siguiente": siguiente,
            "accion": accion,
            "url": self.page.url if self.page and not self.page.is_closed() else None,
            "intento_id": self._intento_actual,
            "timestamp": self._ahora_iso(),
            **extra,
        }
        logger.info("[NAVEGACION_ESATJE] %s", json.dumps(evento, ensure_ascii=False, default=str))
        return evento

    def _interceptar_respuesta_api(self, response):
        try:
            url = response.url.lower()
            if not any(kw in url for kw in ("/api/", "expel", "proceso", "causa", "actuaciones", "catalogo")):
                return
            if any(ext in url for ext in (".js", ".css", ".png", ".ico", ".woff", ".svg")):
                return
            if response.status not in (200, 201):
                return
            if "json" not in response.headers.get("content-type", "").lower():
                return
            self._secuencia_api += 1
            capturado = monotonic()
            request = getattr(response, "request", None)
            self.paquetes_api_interceptados.append({
                "secuencia": self._secuencia_api,
                "capturado_monotonic": capturado,
                "url": response.url,
                "status": response.status,
                "resource_type": getattr(request, "resource_type", None),
                "data": response.json(),
            })
            self._ultima_respuesta_api_monotonic = capturado
        except Exception:
            logger.debug("No se pudo registrar una respuesta API.", exc_info=True)

    def _activar_bloqueo_navegacion(self, causa, descriptor):
        if self._bloqueo_navegacion and self._bloqueo_navegacion.get("activo"):
            raise RuntimeError("BLOQUEO_NAVEGACION_YA_ACTIVO")
        clave = descriptor["clave_carpeta"]
        token = f"{self._intento_actual or 'sin_intento'}:{clave}"
        self._bloqueo_navegacion = {
            "activo": True,
            "token": token,
            "motivo": "EXTRACCION_INFORMACION_PROCESO",
            "causa": self._causa_canonica(causa),
            "clave_carpeta": clave,
            "url_inicio": self.page.url,
            "inicio_monotonic": monotonic(),
        }
        self._cambiar_estado_navegacion(
            causa, self.ultimo_estado_navegacion, "NAVEGACION_BLOQUEADA",
            "bloquear_navegacion", clave_carpeta=clave,
            secuencia_api=self._secuencia_api,
        )
        return token

    def _asegurar_navegacion_permitida(self, operacion, contexto=None):
        bloqueo = self._bloqueo_navegacion
        if not bloqueo or not bloqueo.get("activo"):
            return
        intento = {
            "operacion": operacion,
            "contexto": contexto,
            "bloqueo": dict(bloqueo),
            "timestamp": self._ahora_iso(),
        }
        self._intentos_navegacion_bloqueados.append(intento)
        logger.error("[NAVEGACION_BLOQUEADA] %s", json.dumps(intento, ensure_ascii=False, default=str))
        raise RuntimeError(f"NAVEGACION_BLOQUEADA:{operacion}")

    def _click_navegacion(self, locator, contexto):
        self._asegurar_navegacion_permitida("click", contexto)
        # e-SATJE conserva a veces un overlay Angular aunque el botón BUSCAR
        # ya sea visible y habilitado. Playwright no debe forzar ese clic: la
        # sesión se considera no utilizable y main.py la renovará.
        self._esperar_overlay_inactivo(contexto)
        locator.click()

    def _esperar_overlay_inactivo(self, contexto):
        """Espera una capa de carga breve; falla de forma recuperable si persiste."""
        # Las pruebas unitarias de transiciones usan controles aislados sin
        # una página Playwright; allí el clic ya es el objeto bajo prueba.
        if self.page is None or not hasattr(self.page, "locator"):
            return
        if self.page.is_closed():
            raise RuntimeError("PAGINA_NO_DISPONIBLE")
        limite_ms = int(self.navegacion.get(
            "overlay_carga_timeout_ms",
            self.navegacion.get("retorno_buscador_timeout_ms", 15000),
        ))
        limite = monotonic() + max(1000, limite_ms) / 1000
        selector = (
            "div.loading-overlay[aria-busy='true'], "
            "[role='status'][aria-busy='true'].loading-overlay"
        )
        while monotonic() < limite:
            try:
                visibles = self._locators_visibles(self.page.locator(selector))
            except Exception as exc:
                raise RuntimeError("OVERLAY_CARGA_DIAGNOSTICO_ERROR") from exc
            if not visibles:
                return
            self.page.wait_for_timeout(250)
        raise RuntimeError(f"NAVEGACION_OVERLAY_PERSISTENTE:{contexto}")

    def _go_back_navegacion(self, contexto):
        self._asegurar_navegacion_permitida("go_back", contexto)
        return self.page.go_back()

    def _goto_navegacion(self, url, contexto, **kwargs):
        self._asegurar_navegacion_permitida("goto", contexto)
        return self.page.goto(url, **kwargs)

    def _reload_navegacion(self, contexto, **kwargs):
        self._asegurar_navegacion_permitida("reload", contexto)
        return self.page.reload(**kwargs)

    def _finalizar_bloqueo_navegacion(self, token, manifiesto):
        bloqueo = self._bloqueo_navegacion
        if not bloqueo or not bloqueo.get("activo"):
            raise RuntimeError("BLOQUEO_NAVEGACION_AUSENTE")
        if bloqueo.get("token") != token:
            raise RuntimeError("TOKEN_BLOQUEO_INCONSISTENTE")
        if not manifiesto or not os.path.isfile(manifiesto):
            raise RuntimeError("RESULTADO_CARPETA_NO_DURABLE")
        with open(manifiesto, "r", encoding="utf-8") as archivo:
            resultado = json.load(archivo)
        if resultado.get("estado") not in self.ESTADOS_CARPETA_TERMINALES:
            raise RuntimeError("RESULTADO_CARPETA_TERMINAL_INVALIDO")
        causa = bloqueo["causa"]
        clave = bloqueo["clave_carpeta"]
        duracion = monotonic() - bloqueo["inicio_monotonic"]
        self._bloqueo_navegacion = None
        self._cambiar_estado_navegacion(
            causa, self.ultimo_estado_navegacion, "NAVEGACION_REANUDADA",
            "liberar_navegacion", clave_carpeta=clave,
            manifiesto=manifiesto, duracion_s=round(duracion, 3),
        )

    def _enviar_busqueda_una_vez(self, causa, intento_id):
        clave = (causa, intento_id)
        if clave in self._busquedas_enviadas:
            raise RuntimeError("DOBLE_CLICK_BUSCAR_BLOQUEADO")
        campo = self._input_causa_unico()
        boton = self._boton_buscar_unico()
        if self._causa_canonica(campo.input_value()) != causa:
            raise RuntimeError("CAUSA_CAMBIO_ANTES_DE_BUSCAR")
        if not self._boton_habilitado(boton):
            raise RuntimeError("BUSCAR_NO_HABILITADO")
        self._busquedas_enviadas.add(clave)
        self._click_navegacion(boton, "buscar_causa")
        self._cambiar_estado_navegacion(
            causa, "BUSQUEDA_HABILITADA", "BUSQUEDA_ENVIADA", "click_buscar",
            intento_id=intento_id, click_numero=1,
        )

    def _esperar_boton_buscar_habilitado(self, causa):
        """Espera la habilitación asíncrona del botón antes del clic inicial."""
        limite = monotonic() + (
            self.navegacion.get("captcha_render_timeout_ms", 15000) / 1000
        )
        while monotonic() < limite:
            campo = self._input_causa_unico()
            boton = self._boton_buscar_unico()
            if self._causa_canonica(campo.input_value()) != causa:
                raise RuntimeError("CAUSA_CAMBIO_ANTES_DEL_CLICK_INICIAL_CAPTCHA")
            if self._boton_habilitado(boton):
                return boton
            self.page.wait_for_timeout(250)
        raise PlaywrightTimeoutError("BUSCAR_INICIAL_TIMEOUT_HABILITACION")
    def _activar_captcha_con_click_inicial(self, causa, intento_id):
        """Pulsa BUSCAR para que el portal monte/despliegue el CAPTCHA."""
        if self.page is None:
            return
        campo = self._input_causa_unico()
        boton = self._boton_buscar_unico()
        if self._causa_canonica(campo.input_value()) != causa:
            raise RuntimeError("CAUSA_CAMBIO_ANTES_DEL_CLICK_INICIAL_CAPTCHA")
        limite = monotonic() + (
            self.navegacion.get("captcha_render_timeout_ms", 15000) / 1000
        )
        while not self._boton_habilitado(boton) and monotonic() < limite:
            self.page.wait_for_timeout(250)
            boton = self._boton_buscar_unico()
        if not self._boton_habilitado(boton):
            self._captcha_reinicio_buscador_pendiente = True
            self._cambiar_estado_navegacion(
                causa, "ESPERAR_FIN_CAPTCHA", "CAPTCHA_TIMEOUT",
                "timeout_habilitacion_click_inicial", intento_id=intento_id,
            )
            raise PlaywrightTimeoutError("BUSCAR_INICIAL_TIMEOUT_HABILITACION")
        self._click_navegacion(boton, "activar_captcha")
        self._cambiar_estado_navegacion(
            causa, "ESPERAR_FIN_CAPTCHA", "CAPTCHA_SOLICITADO",
            "click_inicial_buscar", intento_id=intento_id, click_numero=1,
        )
    def _obtener_proveedor_captcha(self):
        if self.proveedor_captcha is not None:
            return self.proveedor_captcha
        variable = str(
            self.captcha_config.get("api_key_env") or "AUTOCAPTCHA_API_KEY"
        ).strip()
        api_key = os.environ.get(variable, "").strip()
        if not api_key:
            raise CaptchaConfiguracionError(
                "CAPTCHA_API_KEY_AUSENTE", recuperable=True
            )
        if str(self.captcha_config.get("proveedor", "2captcha")).lower() != "2captcha":
            raise CaptchaConfiguracionError(
                "CAPTCHA_PROVEEDOR_NO_SOPORTADO", recuperable=False
            )
        self.proveedor_captcha = Proveedor2Captcha(api_key, self.captcha_config)
        return self.proveedor_captcha

    def _diagnosticar_captcha(self):
        return self.page.evaluate("""
            () => {
                const sitekeys = new Set();
                document.querySelectorAll('[data-sitekey]').forEach((elemento) => {
                    const valor = String(elemento.getAttribute('data-sitekey') || '').trim();
                    if (valor) sitekeys.add(valor);
                });
                document.querySelectorAll("iframe[src*='recaptcha']").forEach((iframe) => {
                    try {
                        const valor = new URL(iframe.src, location.href).searchParams.get('k');
                        if (valor) sitekeys.add(valor);
                    } catch (_) {}
                });
                const registros = Object.values(window.__botCaptchaCallbacks || {}).filter(
                    (registro) => {
                        if (!registro.contenedorId) return true;
                        const id = String(registro.contenedorId).replace(/^#/, '');
                        const contenedor = document.getElementById(id);
                        return Boolean(contenedor && contenedor.isConnected);
                    }
                );
                registros.forEach((registro) => {
                    if (registro.sitekey) sitekeys.add(registro.sitekey);
                });
                const texto = String(document.body && document.body.innerText || '').toUpperCase();
                const f5 = /REQUEST REJECTED|THE REQUESTED URL WAS REJECTED|F5 NETWORKS|TSPD/.test(texto);
                const invisibles = Array.from(document.querySelectorAll('[data-size]'))
                    .some((elemento) => String(elemento.getAttribute('data-size')).toLowerCase() === 'invisible');
                return {
                    renderizado: Boolean(document.querySelector(
                        "ngx-recaptcha2, .g-recaptcha, iframe[src*='recaptcha'], textarea[name='g-recaptcha-response']"
                    )),
                    sitekeys: Array.from(sitekeys),
                    widget_ids: registros.map((registro) => String(registro.widgetId)),
                    callbacks_disponibles: registros.filter(
                        (registro) => typeof registro.callback === 'function' &&
                            registro.callbackOriginalDisponible
                    ).length,
                    invisible: invisibles,
                    token_presente: Array.from(document.querySelectorAll(
                        "textarea[name='g-recaptcha-response']"
                    )).some((campo) => Boolean(String(campo.value || campo.textContent || '').trim())),
                    f5_tspd_detectado: f5,
                    url: location.href
                };
            }
        """)

    def _obtener_desafio_captcha(self, causa):
        limite = monotonic() + (
            float(self.navegacion.get("captcha_render_timeout_ms", 15000)) / 1000
        )
        ultimo = None
        while monotonic() < limite:
            ultimo = self._diagnosticar_captcha()
            if ultimo.get("f5_tspd_detectado"):
                raise CaptchaConfiguracionError(
                    "CAPTCHA_F5_TSPD_FUERA_DE_ALCANCE", recuperable=False
                )
            sitekeys = ultimo.get("sitekeys") or []
            widgets = ultimo.get("widget_ids") or []
            if (
                ultimo.get("renderizado") and len(sitekeys) == 1
                and len(widgets) == 1 and ultimo.get("callbacks_disponibles") == 1
            ):
                desafio = CaptchaDesafio(
                    tipo="recaptcha_v2",
                    website_url=ultimo.get("url") or self.page.url,
                    sitekey=sitekeys[0],
                    widget_id=widgets[0],
                    invisible=bool(ultimo.get("invisible")),
                )
                import hashlib
                huella = hashlib.sha256(
                    f"{desafio.website_url}|{desafio.sitekey}|{desafio.widget_id}".encode("utf-8")
                ).hexdigest()[:16]
                logger.info(
                    "[CAPTCHA] Desafío diagnosticado para %s: tipo=%s widget_hash=%s",
                    causa, desafio.tipo, huella,
                )
                return desafio, huella
            self.page.wait_for_timeout(250)
        raise CaptchaConfiguracionError(
            "CAPTCHA_DESCRIPTOR_O_CALLBACK_INVALIDO", recuperable=True
        )

    def _aplicar_solucion_captcha(self, causa, desafio, solucion):
        resultado = self.page.evaluate("""
            ({token, widgetId}) => {
                const registros = window.__botCaptchaCallbacks || {};
                const registro = registros[String(widgetId)];
                if (!registro || typeof registro.callback !== 'function' ||
                    !registro.callbackOriginalDisponible) {
                    return {aplicado: false, motivo: 'CALLBACK_AUSENTE'};
                }
                if (registro.inyectadoPorBot) {
                    return {aplicado: false, motivo: 'TOKEN_YA_INYECTADO'};
                }
                const campos = Array.from(document.querySelectorAll(
                    "textarea[name='g-recaptcha-response']"
                ));
                if (!campos.length) {
                    return {aplicado: false, motivo: 'CAMPO_RESPUESTA_AUSENTE'};
                }
                const descriptor = Object.getOwnPropertyDescriptor(
                    HTMLTextAreaElement.prototype, 'value'
                );
                campos.forEach((campo) => {
                    if (descriptor && descriptor.set) descriptor.set.call(campo, token);
                    else campo.value = token;
                    campo.textContent = token;
                    campo.dispatchEvent(new Event('input', {bubbles: true}));
                    campo.dispatchEvent(new Event('change', {bubbles: true}));
                });
                registro.inyectadoPorBot = true;
                registro.callback(token);
                return {
                    aplicado: true,
                    callback_invocado: true,
                    campos_actualizados: campos.length,
                    widget_id: String(widgetId)
                };
            }
        """, {"token": solucion.token, "widgetId": desafio.widget_id})
        if not resultado.get("aplicado") or not resultado.get("callback_invocado"):
            raise CaptchaProveedorError(
                "CAPTCHA_INYECCION_NO_CONFIRMADA:%s" % resultado.get("motivo", "DESCONOCIDO"),
                recuperable=True,
            )
        if self._causa_canonica(self._input_causa_unico().input_value()) != causa:
            raise CaptchaProveedorError(
                "CAPTCHA_CAUSA_CAMBIO_DURANTE_INYECCION", recuperable=True
            )
        logger.info(
            "[CAPTCHA] Token entregado a Angular para %s: task_id=%s widget_id=%s",
            causa, solucion.task_id, desafio.widget_id,
        )
        return resultado

    def _registrar_error_proveedor_captcha(self):
        self._captcha_errores_consecutivos += 1
        maximo = max(1, int(self.captcha_config.get("max_errores_consecutivos", 3)))
        if self._captcha_errores_consecutivos >= maximo:
            self._captcha_circuito_abierto = True

    def _resolver_o_esperar_captcha(self, causa, intento_id):
        modo = str(
            self.captcha_config.get("modo", "api_con_espera_humana_limitada")
        ).strip().lower()
        self._captcha_solucion_actual = None
        logger.info(
            "[CAPTCHA] Inicio de resolucion para %s: modo=%s proveedor=%s.",
            causa, modo, self.captcha_config.get("proveedor", "2captcha"),
        )
        if modo == "manual":
            raise CaptchaConfiguracionError("CAPTCHA_MODO_MANUAL_NO_ADMITIDO")
        try:
            if self._captcha_circuito_abierto:
                raise CaptchaProveedorError(
                    "CAPTCHA_CIRCUITO_ABIERTO", recuperable=False
                )
            proveedor = self._obtener_proveedor_captcha()
            if not self._captcha_disponibilidad_verificada:
                proveedor.comprobar_disponibilidad()
                self._captcha_disponibilidad_verificada = True
                logger.info("[CAPTCHA] Proveedor 2Captcha disponible; credencial validada.")
            desafio, huella = self._obtener_desafio_captcha(causa)
            tareas = self._captcha_tareas_por_causa.get(causa, 0)
            maximo = max(1, int(self.captcha_config.get("max_tareas_por_causa", 2)))
            if tareas >= maximo:
                raise CaptchaProveedorError(
                    "CAPTCHA_PRESUPUESTO_CAUSA_AGOTADO", recuperable=False
                )
            if huella in self._captcha_tareas_activas:
                raise CaptchaProveedorError(
                    "CAPTCHA_TAREA_DUPLICADA_BLOQUEADA", recuperable=False
                )
            self._captcha_tareas_por_causa[causa] = tareas + 1
            self._captcha_tareas_activas.add(huella)
            try:
                solucion = proveedor.resolver(
                    desafio, {"intento_id": intento_id, "tarea_numero": tareas + 1}
                )
            finally:
                self._captcha_tareas_activas.discard(huella)
            self._aplicar_solucion_captcha(causa, desafio, solucion)
            self._captcha_solucion_actual = solucion
            boton = self._esperar_busqueda_habilitada(causa)
            self._captcha_errores_consecutivos = 0
            logger.info(
                "[CAPTCHA] Solución confirmada para %s: task_id=%s latencia_ms=%s costo_usd=%s",
                causa, solucion.task_id, solucion.latencia_ms, solucion.costo_usd,
            )
            return boton
        except CaptchaError as exc:
            self._captcha_reinicio_buscador_pendiente = True
            if not isinstance(exc, CaptchaConfiguracionError):
                self._registrar_error_proveedor_captcha()
            espera_humana_limitada = modo in {
                "api_con_espera_humana_limitada",
                # Compatibilidad con configuraciones anteriores: ya no abre
                # una espera ilimitada; aplica exactamente la misma ventana.
                "api_con_fallback_manual",
            }
            logger.warning(
                "[CAPTCHA] Fallo controlado para %s: %s; espera_humana_30s=%s",
                causa, exc.codigo, espera_humana_limitada,
            )
            if espera_humana_limitada:
                self._captcha_solucion_actual = None
                # Nunca retener el lote mas de treinta segundos por una
                # intervencion humana; una configuracion mayor se limita.
                espera_ms = min(
                    30000,
                    max(0, int(self.captcha_config.get("espera_humana_maxima_ms", 30000))),
                )
                logger.warning(
                    "[CAPTCHA] La API no resolvio %s. Hay %s segundos para "
                    "completarlo en el navegador; luego se enviara a revision manual.",
                    causa, espera_ms / 1000,
                )
                return self._esperar_busqueda_habilitada(
                    causa,
                    timeout_ms=espera_ms,
                    accion_timeout="espera_humana_limitada_expirada",
                    codigo_timeout="CAPTCHA_ESPERA_MANUAL_30S_AGOTADA",
                )
            raise

    def _esperar_despues_captcha(self, causa):
        espera_ms = max(0, int(self.captcha_config.get("espera_post_solucion_ms", 500)))
        if espera_ms:
            logger.info(
                "[CAPTCHA] Esperando %s segundos antes de BUSCAR para %s.",
                espera_ms / 1000, causa,
            )
            self.page.wait_for_timeout(espera_ms)
        campo = self._input_causa_unico()
        boton = self._boton_buscar_unico()
        if self._causa_canonica(campo.input_value()) != causa:
            raise RuntimeError("CAUSA_CAMBIO_DURANTE_ESPERA_POST_CAPTCHA")
        if not self._boton_habilitado(boton):
            if self._captcha_visible():
                raise RuntimeError("CAPTCHA_PERDIDO_DURANTE_ESPERA_POST_SOLUCION")
            raise RuntimeError("BUSCAR_SE_DESHABILITO_DURANTE_ESPERA_POST_CAPTCHA")
        if self._captcha_solucion_actual is None and self._captcha_visible():
            raise RuntimeError("CAPTCHA_PERDIDO_DURANTE_ESPERA_POST_SOLUCION")
        return boton

    def _reportar_solucion_captcha(self, correcta, rechazo_confirmado=False):
        solucion = self._captcha_solucion_actual
        self._captcha_solucion_actual = None
        if solucion is None or self.proveedor_captcha is None:
            return False
        if not correcta and not rechazo_confirmado:
            return False
        habilitado = self.captcha_config.get(
            "reportar_correcta" if correcta else "reportar_incorrecta", True
        )
        if not habilitado:
            return False
        try:
            metodo = (
                self.proveedor_captcha.reportar_correcta
                if correcta else self.proveedor_captcha.reportar_incorrecta
            )
            reportado = metodo(solucion.task_id)
            logger.info(
                "[CAPTCHA] Resultado reportado: task_id=%s correcta=%s reportado=%s",
                solucion.task_id, correcta, reportado,
            )
            return reportado
        except CaptchaError as exc:
            logger.warning(
                "[CAPTCHA] No se pudo reportar task_id=%s: %s",
                solucion.task_id, exc.codigo,
            )
            return False

    def _diagnostico_busqueda(self, causa, intento_numero, error):
        diagnostico = {
            "causa": self._causa_canonica(causa),
            "intento_global": self._intento_actual,
            "intento_busqueda": intento_numero,
            "estado_navegacion": self.ultimo_estado_navegacion,
            "error": str(error),
            "url": None,
            "valor_campo": None,
            "texto_portal": None,
            "timestamp": self._ahora_iso(),
        }
        try:
            diagnostico["url"] = self.page.url
        except Exception:
            pass
        try:
            diagnostico["valor_campo"] = self._input_causa_unico().input_value()
        except Exception:
            pass
        try:
            texto = re.sub(r"\s+", " ", self.page.inner_text("body")).strip()
            diagnostico["texto_portal"] = texto[:4000]
            diagnostico["motivo_rechazo"] = self._motivo_rechazo_formulario(texto)
        except Exception:
            pass
        return diagnostico

    def _guardar_evidencia_busqueda(self, causa, intento_numero, error):
        """Persiste el estado de cada rechazo/timeout sin alterar la navegación."""
        try:
            intento = self._clave_archivo(self._intento_actual or "sin_intento")
            directorio = os.path.join(
                "data", "temp_htmls", self._causa_canonica(causa), intento,
                f"busqueda_{intento_numero:02d}",
            )
            os.makedirs(directorio, exist_ok=True)
            rutas = {}
            diagnostico = self._diagnostico_busqueda(causa, intento_numero, error)
            ruta_json = os.path.join(directorio, "diagnostic.json")
            self._escribir_json_atomico(ruta_json, diagnostico)
            rutas["diagnostico"] = ruta_json
            if self.page and not self.page.is_closed():
                try:
                    ruta_html = os.path.join(directorio, "page.html")
                    contenido = self.page.content()
                    contenido = re.sub(
                        r"(<textarea[^>]*name=['\"]g-recaptcha-response['\"][^>]*>).*?(</textarea>)",
                        r"\1&lt;redactado&gt;\2", contenido,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    with open(ruta_html, "w", encoding="utf-8") as archivo:
                        archivo.write(contenido)
                    rutas["html"] = ruta_html
                except Exception:
                    logger.debug("No se pudo guardar HTML de búsqueda.", exc_info=True)
                try:
                    ruta_screen = os.path.join(directorio, "screen.png")
                    self.page.screenshot(path=ruta_screen, full_page=True)
                    rutas["screenshot"] = ruta_screen
                except Exception:
                    logger.debug("No se pudo guardar captura de búsqueda.", exc_info=True)
            return rutas
        except Exception:
            logger.warning("No se pudo guardar evidencia de búsqueda.", exc_info=True)
            return {}

    def _buscar_resultado_con_reintentos(self, causa_original, causa):
        max_intentos = max(1, int(self.navegacion["max_reintentos_transicion"]))
        ultimo_error = None
        for intento_numero in range(1, max_intentos + 1):
            if intento_numero > 1:
                estado = self.ultimo_estado_navegacion
                self._cambiar_estado_navegacion(
                    causa, estado, "PREPARAR_BUSCADOR", "reintentar_busqueda",
                    intento_busqueda=intento_numero,
                    error_anterior=str(ultimo_error),
                )
            self._preparar_busqueda(causa_original)
            self._cambiar_estado_navegacion(
                causa, "CAUSA_ESCRITA", "ESPERAR_FIN_CAPTCHA",
                "esperar_buscar_habilitado", intento_busqueda=intento_numero,
            )
            intento_id = f"{self._intento_actual}:busqueda-{intento_numero}"
            self._activar_captcha_con_click_inicial(causa, intento_id)
            self._resolver_o_esperar_captcha(causa, intento_id)
            self._esperar_despues_captcha(causa)
            self._enviar_busqueda_una_vez(causa, intento_id)
            try:
                resultado = self._esperar_resultados(causa)
                self._reportar_solucion_captcha(correcta=True)
                return resultado
            except (PlaywrightTimeoutError, RuntimeError) as exc:
                reintentable = str(exc) in {
                    "RESULTADOS_TIMEOUT", "BUSQUEDA_RECHAZADA_FORMULARIO",
                }
                if not reintentable:
                    raise
                ultimo_error = exc
                if str(exc) == "BUSQUEDA_RECHAZADA_FORMULARIO":
                    try:
                        rechazo_confirmado = self._captcha_visible()
                    except Exception:
                        rechazo_confirmado = False
                    self._reportar_solucion_captcha(
                        correcta=False, rechazo_confirmado=rechazo_confirmado
                    )
                else:
                    self._captcha_solucion_actual = None
                if str(exc) == "RESULTADOS_TIMEOUT" and self.ultimo_estado_navegacion == "BUSQUEDA_ENVIADA":
                    self._cambiar_estado_navegacion(
                        causa, "BUSQUEDA_ENVIADA", "BUSQUEDA_TIMEOUT",
                        "timeout_resultados", intento_busqueda=intento_numero,
                    )
                evidencia = self._guardar_evidencia_busqueda(
                    causa, intento_numero, exc
                )
                logger.warning(
                    "[NAVEGACION_ESATJE] Búsqueda %s/%s rechazada para %s: %s. Evidencia: %s",
                    intento_numero, max_intentos, causa, exc, evidencia,
                )
                # El portal puede quedarse indefinidamente con la capa
                # "Buscando..." encima del formulario. Reintentar dentro de
                # la misma p\u00e1gina solo encadena timeouts: los clics posteriores
                # quedan interceptados por esa capa. Se aborta la causa para
                # que el orquestador reinicie la sesi\u00f3n antes de la siguiente.
                if (
                    str(exc) == "RESULTADOS_TIMEOUT"
                    and self._hay_carga_visible()
                ):
                    logger.error(
                        "[NAVEGACION_ESATJE] Carga persistente tras timeout de %s; "
                        "se requiere reiniciar la sesi\u00f3n.",
                        causa,
                    )
                    raise RuntimeError("BUSQUEDA_BLOQUEADA_CARGA_PERSISTENTE")
                if intento_numero >= max_intentos:
                    raise
        raise ultimo_error or RuntimeError("BUSQUEDA_SIN_RESULTADO")

    def _abrir_movimientos_causa(self, causa, resultado):
        self._cambiar_estado_navegacion(
            causa, "RESULTADOS_LISTOS", "ABRIENDO_MOVIMIENTOS", "localizar_movimientos"
        )
        causa = self._causa_canonica(causa)
        if not self._fila_corresponde_causa(resultado, causa):
            raise RuntimeError("FILA_NO_CORRESPONDE_A_CAUSA")
        enlaces = resultado.locator(
            "a[aria-label*='movimientos' i], a[href*='/movimientos'], "
            "a:has(mat-icon:has-text('folder_open'))"
        )
        visibles = [
            enlaces.nth(indice) for indice in range(enlaces.count())
            if enlaces.nth(indice).is_visible()
        ]
        if len(visibles) != 1:
            raise RuntimeError("ENLACE_MOVIMIENTOS_FILA_AUSENTE_O_AMBIGUO")
        enlace = visibles[0]
        etiqueta = enlace.get_attribute("aria-label") or ""
        if etiqueta and not self._texto_contiene_causa_numerica_exacta(etiqueta, causa):
            raise RuntimeError("ENLACE_MOVIMIENTOS_NO_CORRESPONDE_A_CAUSA")
        self._click_navegacion(enlace, "abrir_movimientos_causa")
        self._cambiar_estado_navegacion(
            causa, "ABRIENDO_MOVIMIENTOS", "MOVIMIENTOS_CARGANDO", "click_movimientos"
        )
        self.page.wait_for_url(
            re.compile(r"/movimientos(?:[/?#]|$)"),
            timeout=self.navegacion["movimientos_timeout_ms"],
        )

    def _hay_carga_visible(self):
        selectores = (
            "mat-spinner", "mat-progress-spinner", "[role='progressbar']",
            ".loading", ".loading-overlay", ".spinner",
            "[role='status'][aria-busy='true']", "[aria-busy='true']",
            "text=/^\\s*Buscando\\.\\.\\.\\s*$/i",
        )
        for selector in selectores:
            try:
                elementos = self.page.locator(selector)
                for indice in range(elementos.count()):
                    if elementos.nth(indice).is_visible():
                        return True
            except Exception:
                continue
        return False

    @staticmethod
    def _texto_locator(locator):
        try:
            return " ".join(locator.inner_text().split())
        except Exception:
            return ""

    @staticmethod
    def _normalizar_texto(texto):
        import unicodedata
        return "".join(
            caracter for caracter in unicodedata.normalize("NFD", str(texto).upper())
            if unicodedata.category(caracter) != "Mn"
        )

    def _firma_movimientos(self):
        dependencias = self.page.locator(".lista-movimientos-causa .movimiento-individual")
        incidentes = self.page.locator(".lista-movimientos-causa .lista-movimiento-individual")
        filas = []
        for indice in range(incidentes.count()):
            fila = incidentes.nth(indice)
            try:
                if not fila.is_visible():
                    continue
                enlace = fila.locator("a[href*='/actuaciones']")
                hrefs = [enlace.nth(i).get_attribute("href") for i in range(enlace.count())]
                filas.append((self._texto_locator(fila), tuple(hrefs)))
            except Exception:
                continue
        return (dependencias.count(), len(filas), tuple(filas), self._hay_carga_visible())

    def _esperar_movimientos_listos(self, causa):
        limite = monotonic() + (self.navegacion["movimientos_timeout_ms"] / 1000)
        estable = 0
        firma_anterior = None
        while monotonic() < limite:
            texto = self.page.inner_text("body")
            valido = (
                self._ruta_es(self.page.url, "/movimientos")
                and not self._hay_carga_visible()
                and "DATOS GENERALES" in self._normalizar_texto(texto)
                and "ACTUACIONES JUDICIALES" in self._normalizar_texto(texto)
                and causa in self._causa_canonica(texto)
                and self.page.locator(".lista-movimientos-causa").count() == 1
            )
            firma = self._firma_movimientos() if valido else None
            if valido and firma == firma_anterior:
                estable += 1
                if estable >= int(self.navegacion["comprobaciones_estables"]):
                    self._cambiar_estado_navegacion(
                        causa, "MOVIMIENTOS_CARGANDO", "MOVIMIENTOS_LISTOS",
                        "validar_movimientos", firma=firma,
                    )
                    return firma
            else:
                estable = 0
            firma_anterior = firma
            self.page.wait_for_timeout(self.navegacion["sondeo_estabilidad_ms"])
        raise PlaywrightTimeoutError("MOVIMIENTOS_TIMEOUT")

    def _descriptor_incidente(self, causa, dependencia, incidente):
        import hashlib
        dependencia_texto = self._texto_locator(dependencia)
        incidente_texto = self._texto_locator(incidente)
        enlaces = incidente.locator("a[href*='/actuaciones']")
        visibles = []
        for indice in range(enlaces.count()):
            enlace = enlaces.nth(indice)
            if enlace.is_visible() and enlace.is_enabled():
                visibles.append(enlace)
        if len(visibles) != 1:
            raise RuntimeError("CARPETA_PROCESAL_AMBIGUA")
        enlace = visibles[0]
        href = enlace.get_attribute("href") or ""
        numero = self._texto_locator(incidente.locator(".numero-incidente").first)
        fecha = self._texto_locator(incidente.locator(".fecha-ingreso").first)
        actores = self._texto_locator(incidente.locator(".lista-actores").first)
        demandados = self._texto_locator(incidente.locator(".lista-demandados").first)
        dependencia_match = re.search(
            r"DEPENDENCIA JURISDICCIONAL:\s*(.*?)(?=\s+CIUDAD:|$)",
            dependencia_texto, re.IGNORECASE,
        )
        ciudad_match = re.search(r"CIUDAD:\s*(.*?)(?=\s+\d{1,3}\s+\d{2}/\d{2}/\d{4}|$)", dependencia_texto, re.IGNORECASE)
        nombre_dependencia = dependencia_match.group(1).strip() if dependencia_match else dependencia_texto
        ciudad = ciudad_match.group(1).strip() if ciudad_match else None
        base_clave = "|".join((causa, nombre_dependencia.upper(), numero, fecha, incidente_texto.upper()))
        digest = hashlib.sha256(base_clave.encode("utf-8")).hexdigest()[:12]
        clave = self._clave_archivo(f"{causa}_{numero}_{fecha}_{digest}")
        return {
            "causa": causa,
            "dependencia": nombre_dependencia,
            "ciudad": ciudad,
            "numero_incidente": numero,
            "fecha_ingreso": fecha,
            "actores": actores,
            "demandados": demandados,
            "texto_normalizado": incidente_texto,
            "href_actuaciones": href,
            "id_api": None,
            "clave_carpeta": clave,
        }, enlace

    def _descubrir_carpetas_procesales(self, causa):
        if not self._ruta_es(self.page.url, "/movimientos"):
            raise RuntimeError("PANTALLA_MOVIMIENTOS_REQUERIDA")
        dependencias = self.page.locator(".lista-movimientos-causa .movimiento-individual")
        descriptores = []
        claves = set()
        for indice_dependencia in range(dependencias.count()):
            dependencia = dependencias.nth(indice_dependencia)
            if not dependencia.is_visible():
                continue
            incidentes = dependencia.locator(".lista-movimiento-individual")
            for indice_incidente in range(incidentes.count()):
                incidente = incidentes.nth(indice_incidente)
                if not incidente.is_visible():
                    continue
                descriptor, _ = self._descriptor_incidente(causa, dependencia, incidente)
                descriptor["indice_visual_dependencia"] = indice_dependencia
                descriptor["indice_visual_incidente"] = indice_incidente
                if descriptor["clave_carpeta"] in claves:
                    raise RuntimeError("CARPETA_PROCESAL_AMBIGUA")
                claves.add(descriptor["clave_carpeta"])
                descriptores.append(descriptor)
        if not descriptores:
            raise RuntimeError("CARPETA_PROCESAL_AUSENTE")
        self._cambiar_estado_navegacion(
            causa, "MOVIMIENTOS_LISTOS", "CARPETAS_DESCUBIERTAS",
            "descubrir_carpetas", cantidad=len(descriptores),
            claves=[d["clave_carpeta"] for d in descriptores],
        )
        return descriptores

    def _localizar_carpeta_procesal(self, causa, descriptor_buscado):
        dependencias = self.page.locator(".lista-movimientos-causa .movimiento-individual")
        coincidencias = []
        for indice_dependencia in range(dependencias.count()):
            dependencia = dependencias.nth(indice_dependencia)
            incidentes = dependencia.locator(".lista-movimiento-individual")
            for indice_incidente in range(incidentes.count()):
                incidente = incidentes.nth(indice_incidente)
                try:
                    descriptor, enlace = self._descriptor_incidente(causa, dependencia, incidente)
                    if descriptor["clave_carpeta"] == descriptor_buscado["clave_carpeta"]:
                        coincidencias.append((incidente, enlace))
                except RuntimeError:
                    continue
        if len(coincidencias) != 1:
            raise RuntimeError("CARPETA_NO_RELOCALIZABLE")
        return coincidencias[0]

    def _firma_api_actuaciones_lista(self, causa, secuencia_inicio):
        """Devuelve una firma durable cuando la API ya entrego las actuaciones.

        La respuesta JSON se captura completa antes de incorporarse a
        ``paquetes_api_interceptados``. Esto permite continuar aunque Angular
        siga renderizando una lista extensa, sin relajar la correspondencia de
        causa ni la ventana transaccional iniciada por el clic de carpeta.
        """
        paquetes = self._paquetes_ventana(
            secuencia_inicio, self._secuencia_api, causa
        )
        actuaciones = self._extraer_actuaciones_api(paquetes)
        if not paquetes or not actuaciones:
            return None
        ultima_captura = max(
            float(paquete.get("capturado_monotonic", 0.0) or 0.0)
            for paquete in paquetes
        )
        quietud_ms = (monotonic() - ultima_captura) * 1000
        if quietud_ms < self.navegacion["quietud_api_ms"]:
            return None
        secuencias = [int(paquete.get("secuencia", 0)) for paquete in paquetes]
        return (
            causa,
            "API_ACTUACIONES",
            len(actuaciones),
            min(secuencias),
            max(secuencias),
            round(quietud_ms, 1),
        )

    def _esperar_informacion_proceso_y_bloquear(
        self, causa, descriptor, secuencia_inicio=None
    ):
        if secuencia_inicio is None:
            secuencia_inicio = self._secuencia_api
        limite = monotonic() + (self.navegacion["actuaciones_timeout_ms"] / 1000)
        while monotonic() < limite:
            firma_api = None
            if self._ruta_es(self.page.url, "/actuaciones"):
                firma_api = self._firma_api_actuaciones_lista(
                    causa, secuencia_inicio
                )
            if firma_api:
                self._cambiar_estado_navegacion(
                    causa, "INFORMACION_PROCESO_CARGANDO", "INFORMACION_PROCESO_LISTA",
                    "validar_informacion_proceso", clave_carpeta=descriptor["clave_carpeta"],
                    fuente_listo="api", actuaciones_api=firma_api[2],
                )
                return self._activar_bloqueo_navegacion(causa, descriptor)
            texto = self.page.inner_text("body")
            texto_upper = self._normalizar_texto(texto)
            controles = any(senal in texto_upper for senal in ("EXPORTAR PDF", "AMPLIAR TODO", "CONTRAER TODO"))
            if (
                self._ruta_es(self.page.url, "/actuaciones")
                and "INFORMACION DEL PROCESO" in texto_upper
                and causa in self._causa_canonica(texto)
                and controles
                and not self._hay_carga_visible()
            ):
                self._cambiar_estado_navegacion(
                    causa, "INFORMACION_PROCESO_CARGANDO", "INFORMACION_PROCESO_LISTA",
                    "validar_informacion_proceso", clave_carpeta=descriptor["clave_carpeta"],
                    fuente_listo="dom",
                )
                return self._activar_bloqueo_navegacion(causa, descriptor)
            self.page.wait_for_timeout(self.navegacion["sondeo_estabilidad_ms"])
        raise PlaywrightTimeoutError("INFORMACION_PROCESO_TIMEOUT")

    def _firma_actuaciones(self, causa):
        texto = self.page.inner_text("body")
        filas = self.page.locator(
            "expel-listado-actuaciones .fila, .lista-actuaciones .mat-expansion-panel, "
            ".actuacion-item, table tbody tr"
        )
        textos = []
        for indice in range(filas.count()):
            fila = filas.nth(indice)
            try:
                if fila.is_visible():
                    contenido = self._texto_locator(fila)
                    if contenido:
                        textos.append(contenido)
            except Exception:
                continue
        fechas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto)
        adjuntos = self.page.locator("[mattooltip='Ver archivos'][role='link'], [mattooltip='Ver archivos']")
        return (
            causa, len(textos), len(fechas), len(" ".join(texto.split())),
            textos[0][:160] if textos else None,
            textos[-1][:160] if textos else None,
            adjuntos.count(), self._secuencia_api, self._hay_carga_visible(),
        )

    def _esperar_actuaciones_estables(self, causa, secuencia_inicio=None):
        limite = monotonic() + (self.navegacion["pantalla_final_timeout_ms"] / 1000)
        estable = 0
        firma_anterior = None
        while monotonic() < limite:
            if not self._ruta_es(self.page.url, "/actuaciones"):
                raise RuntimeError("INFORMACION_PROCESO_URL_CAMBIO_DURANTE_EXTRACCION")
            if secuencia_inicio is not None:
                firma_api = self._firma_api_actuaciones_lista(
                    causa, secuencia_inicio
                )
                if firma_api:
                    return firma_api
            firma = self._firma_actuaciones(causa)
            quietud = (monotonic() - self._ultima_respuesta_api_monotonic) * 1000 >= self.navegacion["quietud_api_ms"]
            if not firma[-1] and firma == firma_anterior and quietud:
                estable += 1
                if estable >= int(self.navegacion["comprobaciones_estables"]):
                    return firma
            else:
                estable = 0
            firma_anterior = firma
            self.page.wait_for_timeout(self.navegacion["sondeo_estabilidad_ms"])
        raise PlaywrightTimeoutError("PANTALLA_ACTUACIONES_NO_ESTABLE")

    def _paquetes_ventana(self, secuencia_inicio, secuencia_fin, causa):
        paquetes = [
            paquete for paquete in self.paquetes_api_interceptados
            if secuencia_inicio < int(paquete.get("secuencia", 0)) <= secuencia_fin
        ]
        return self._paquetes_api_de_carpeta(paquetes, causa)

    @staticmethod
    def _extraer_actuaciones_api(paquetes):
        actuaciones = []
        vistos = set()

        def recorrer(valor):
            if isinstance(valor, list):
                for item in valor:
                    recorrer(item)
                return
            if not isinstance(valor, dict):
                return
            campo_detalle = next((
                campo for campo in (
                    "actuacion", "detalle", "tipoActuacion", "actividad"
                ) if valor.get(campo)
            ), None)
            detalle = valor.get(campo_detalle) if campo_detalle else None
            fecha = next((valor.get(campo) for campo in (
                "fecha", "fechaActuacion", "fechaProvidencia", "fechaCrea",
                "fechaCreacion", "fechaRegistro", "fechaIngreso"
            ) if valor.get(campo)), None)
            if detalle:
                detalle_literal = str(detalle).strip()
                clave = (str(fecha) if fecha else None, detalle_literal.upper())
                if clave not in vistos:
                    vistos.add(clave)
                    actuacion = {"fecha": clave[0], "detalle": clave[1]}
                    if campo_detalle in {"actuacion", "tipoActuacion", "actividad"}:
                        actuacion["titulo"] = detalle_literal
                    actuaciones.append(actuacion)
            for clave_hija, hijo in valor.items():
                if clave_hija in {"actuaciones", "listaActuaciones"} or isinstance(hijo, (dict, list)):
                    recorrer(hijo)

        for paquete in paquetes:
            recorrer(paquete.get("data"))
        return actuaciones

    def _ejecutar_extraccion_detalles(
        self, numero_juicio=None, paquetes_api=None, carpeta=None,
        contenido_html=None, demandados=None, adjuntos_por_actuacion=None,
    ):
        """Transforma API/DOM sin hacer clic ni navegar."""
        paquetes = self.paquetes_api_interceptados if paquetes_api is None else paquetes_api
        datos = {
            "FECHA INICIO JUICIO": None,
            "FECHA INICIAL FASE ACTUAL": None,
            "ETAPA_PROCESAL": None,
            "FASE_PROCESAL": None,
            "HISTORIAL_ACTUACIONES": [],
        }
        actuaciones_api = self._extraer_actuaciones_api(paquetes)
        datos_dom = {}
        if contenido_html:
            try:
                datos_dom = self.extractor.procesar_html_string(
                    contenido_html, registrar_decision=False
                ) or {}
            except Exception as exc:
                logger.warning("[RUTA RESPALDO DOM] No se pudo transformar HTML: %s", exc)
        actuaciones_dom = datos_dom.get("HISTORIAL_ACTUACIONES", [])
        actuaciones = []
        por_clave = {}
        for actuacion in list(actuaciones_api) + list(actuaciones_dom):
            clave = (actuacion.get("fecha"), str(actuacion.get("detalle", "")).strip().upper())
            if not clave[1]:
                continue
            existente = por_clave.get(clave)
            if existente is None:
                existente = dict(actuacion)
                por_clave[clave] = existente
                actuaciones.append(existente)
                continue
            # API suele aportar la misma actuación antes que el DOM. Al
            # combinar ambas fuentes se preservan los metadatos exclusivos del
            # DOM, como TIENE_ADJUNTO, que permiten detectar evidencia
            # documental pendiente sin descargar el archivo.
            for campo, valor in actuacion.items():
                if valor not in (None, "", False) and not existente.get(campo):
                    existente[campo] = valor
        self._asociar_nombres_adjuntos(actuaciones, adjuntos_por_actuacion)
        datos.update(datos_dom)
        datos["HISTORIAL_ACTUACIONES"] = actuaciones
        datos["ORIGEN_DATA"] = "API+DOM" if actuaciones_api and actuaciones_dom else ("API" if actuaciones_api else "DOM")
        if actuaciones:
            self._aplicar_inferencia_consolidada(
                datos, causa=numero_juicio, demandados=demandados
            )
        return datos

    @staticmethod
    def _escribir_json_atomico(ruta, contenido):
        temporal = f"{ruta}.tmp"
        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump(contenido, archivo, ensure_ascii=False, indent=2, default=str)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)

    @staticmethod
    def _hash_archivo(ruta):
        import hashlib
        digest = hashlib.sha256()
        with open(ruta, "rb") as archivo:
            for bloque in iter(lambda: archivo.read(65536), b""):
                digest.update(bloque)
        return digest.hexdigest()

    def _guardar_artefactos_carpeta(self, causa, descriptor, paquetes, contenido, frames, resultado, diagnostico):
        intento = self._clave_archivo(self._intento_actual or "sin_intento")
        # El descriptor completo permanece en result.json; el nombre en disco debe
        # ser corto para admitir rutas de ejecucion profundas en Windows.
        clave = "c_" + hashlib.sha256(
            str(descriptor["clave_carpeta"]).encode("utf-8")
        ).hexdigest()[:16]
        directorio = os.path.join("data", "temp_htmls", causa, intento, clave)
        os.makedirs(directorio, exist_ok=True)
        rutas = {}
        ruta_html = os.path.join(directorio, "page.html")
        with open(ruta_html, "w", encoding="utf-8") as archivo:
            archivo.write(contenido or "")
        rutas["html"] = ruta_html
        for indice, frame in enumerate(frames, 1):
            ruta_frame = os.path.join(directorio, f"frame_{indice:03d}.html")
            with open(ruta_frame, "w", encoding="utf-8") as archivo:
                archivo.write(frame)
            rutas.setdefault("frames", []).append(ruta_frame)
        ruta_api = os.path.join(directorio, "api.json")
        self._escribir_json_atomico(ruta_api, paquetes)
        rutas["api"] = ruta_api
        ruta_diagnostico = os.path.join(directorio, "diagnostic.json")
        self._escribir_json_atomico(ruta_diagnostico, diagnostico)
        rutas["diagnostico"] = ruta_diagnostico
        ruta_screen = os.path.join(directorio, "screen.png")
        try:
            self.page.screenshot(path=ruta_screen, full_page=True)
            rutas["screenshot"] = ruta_screen
        except Exception as exc:
            resultado.setdefault("advertencias", []).append(f"SCREENSHOT_ERROR:{exc}")
        hashes = {}
        for nombre, ruta in rutas.items():
            if isinstance(ruta, list):
                hashes[nombre] = [self._hash_archivo(item) for item in ruta]
            else:
                hashes[nombre] = self._hash_archivo(ruta)
        resultado["artefactos"] = rutas
        resultado["hashes"] = hashes
        ruta_resultado = os.path.join(directorio, "result.json")
        self._escribir_json_atomico(ruta_resultado, resultado)
        with open(ruta_resultado, "r", encoding="utf-8") as archivo:
            json.load(archivo)
        return ruta_resultado

    def _capturar_dom_frames(self):
        contenido = self.page.content()
        frames = []
        for frame in self.page.frames:
            try:
                html = frame.content()
                if html and html != contenido:
                    frames.append(html)
            except Exception:
                continue
        return contenido, frames

    @staticmethod
    def _fecha_clave_adjunto(valor):
        """Normaliza una fecha SATJE para asociar fila y actuación."""
        texto = str(valor or "").strip()
        for patron, formato in (
            (r"\b\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
            (r"\b\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
        ):
            encontrado = re.search(patron, texto)
            if not encontrado:
                continue
            try:
                return datetime.strptime(encontrado.group(0), formato).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _es_nombramiento_perito(detalle):
        texto = normalizar_texto(detalle)
        return any(marca in texto for marca in (
            "NOMBRAMIENTO DE PERITO", "ACTA SORTEO PERITO",
            "SORTEO DE PERITO", "SORTEO PERITO", "PERITO LIQUIDADOR NOMBRADO",
        ))

    @staticmethod
    def _es_actuacion_documental_perito(detalle):
        texto = normalizar_texto(detalle)
        return (
            "DOC. GENERAL" in texto
            or "DOC GENERAL" in texto
            or "ESCRITO" in texto
        )

    @staticmethod
    def _es_nombre_evidencia_pago_perito(nombre):
        """Acepta factura o pago que identifique el servicio pericial."""
        texto = normalizar_texto(nombre)
        if "FACTURA" in texto:
            return True
        tiene_pago = any(marca in texto for marca in (
            "PAGO", "COMPROBANTE", "RECIBO", "TRANSFERENCIA", "DEPOSITO",
        ))
        tiene_servicio_pericial = any(marca in texto for marca in (
            "PERITO", "PERICIAL", "LIQUIDADOR", "HONORARIO", "SERVICIO",
            "PROFESIONAL",
        ))
        return tiene_pago and tiene_servicio_pericial

    def _nombres_archivos_dialogo(self, dialogo):
        """Lee los nombres visibles sin descargar documentos de SATJE."""
        nombres = []
        try:
            textos = [linea.strip() for linea in dialogo.inner_text().splitlines()]
        except Exception:
            textos = []
        for texto in textos:
            if self._es_nombre_evidencia_pago_perito(texto):
                nombres.append(texto)
        try:
            enlaces = dialogo.locator("a, button, [role='link']")
            for indice in range(enlaces.count()):
                enlace = enlaces.nth(indice)
                etiqueta = " ".join(str(valor).strip() for valor in (
                    enlace.inner_text(),
                    enlace.get_attribute("title"),
                    enlace.get_attribute("download"),
                    enlace.get_attribute("aria-label"),
                ) if valor).strip()
                if self._es_nombre_evidencia_pago_perito(etiqueta):
                    nombres.append(etiqueta)
        except Exception:
            pass
        return list(dict.fromkeys(nombre for nombre in nombres if nombre))

    def _cerrar_dialogo_adjuntos(self, dialogo):
        try:
            cierre = dialogo.locator(
                "button[aria-label*='cerrar' i], button[title*='cerrar' i], "
                "button:has-text('Cerrar'), [mattooltip*='Cerrar' i]"
            )
            if cierre.count():
                cierre.first.click()
                self.page.wait_for_timeout(150)
                return
        except Exception:
            pass
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(150)
        except Exception:
            pass

    def _capturar_adjuntos_pago_perito(self, contenido_html):
        """Obtiene evidencia de pago en actuaciones posteriores al perito.

        Solo abre el listado de archivos de la actuación, sin descargar ni
        leer los documentos. La ausencia de evidencia no altera la fecha.
        """
        try:
            datos = self.extractor.procesar_html_string(
                contenido_html, registrar_decision=False
            ) or {}
        except Exception:
            return []
        actuaciones = datos.get("HISTORIAL_ACTUACIONES") or []
        fechas_nombramiento = [
            self._fecha_clave_adjunto(actuacion.get("fecha"))
            for actuacion in actuaciones
            if self._es_nombramiento_perito(actuacion.get("detalle"))
        ]
        fechas_nombramiento = [fecha for fecha in fechas_nombramiento if fecha]
        if not fechas_nombramiento:
            return []
        fecha_nombramiento = max(fechas_nombramiento)

        filas = self.page.locator("table tbody tr, table tr, [role='row'], mat-row, .fila")
        hallazgos = []
        vistos = set()
        for indice in range(filas.count()):
            fila = filas.nth(indice)
            try:
                texto_fila = fila.inner_text()
                fecha = self._fecha_clave_adjunto(texto_fila)
                if (
                    not fecha or fecha < fecha_nombramiento
                    or not self._es_actuacion_documental_perito(texto_fila)
                ):
                    continue
                boton = fila.locator(
                    "[mattooltip='Ver archivos'], [mattooltip*='Ver archivo' i], "
                    "[aria-label*='ver archivo' i], [aria-label*='archivos' i]"
                )
                if boton.count() != 1:
                    continue
                boton.first.click()
                self.page.wait_for_timeout(200)
                dialogos = self.page.locator("mat-dialog-container, [role='dialog']")
                dialogo = None
                for posicion in range(dialogos.count() - 1, -1, -1):
                    candidato = dialogos.nth(posicion)
                    if candidato.is_visible():
                        dialogo = candidato
                        break
                if dialogo is None:
                    continue
                nombres = self._nombres_archivos_dialogo(dialogo)
                self._cerrar_dialogo_adjuntos(dialogo)
                if not nombres:
                    continue
                clave = (fecha, normalizar_texto(texto_fila)[:160])
                if clave not in vistos:
                    vistos.add(clave)
                    hallazgos.append({
                        "fecha": fecha,
                        "detalle_fila": texto_fila,
                        "NOMBRES_ADJUNTOS": nombres,
                    })
            except Exception as exc:
                logger.debug("No se pudieron leer adjuntos de una actuación: %s", exc)
        return hallazgos

    def _asociar_nombres_adjuntos(self, actuaciones, adjuntos_por_actuacion):
        """Propaga nombres de archivo a la actuación persistida equivalente."""
        for metadato in adjuntos_por_actuacion or []:
            fecha = self._fecha_clave_adjunto(metadato.get("fecha"))
            texto_fila = normalizar_texto(metadato.get("detalle_fila"))
            for actuacion in actuaciones:
                if self._fecha_clave_adjunto(actuacion.get("fecha")) != fecha:
                    continue
                detalle = normalizar_texto(actuacion.get("detalle"))
                if not detalle or not (detalle in texto_fila or texto_fila in detalle):
                    continue
                existentes = actuacion.get("NOMBRES_ADJUNTOS") or []
                if isinstance(existentes, str):
                    existentes = [existentes]
                actuacion["NOMBRES_ADJUNTOS"] = list(dict.fromkeys(
                    [*existentes, *(metadato.get("NOMBRES_ADJUNTOS") or [])]
                ))
                actuacion["TIENE_ADJUNTO"] = True
                break

    def _extraer_informacion_proceso(self, causa, descriptor, secuencia_inicio, token):
        inicio = monotonic()
        manifiesto = None
        resultado = None
        try:
            firma = self._esperar_actuaciones_estables(causa, secuencia_inicio)
            secuencia_fin = self._secuencia_api
            paquetes = self._paquetes_ventana(secuencia_inicio, secuencia_fin, causa)
            contenido, frames = self._capturar_dom_frames()
            adjuntos_perito = self._capturar_adjuntos_pago_perito(contenido)
            datos = self._ejecutar_extraccion_detalles(
                causa, paquetes_api=paquetes,
                carpeta=descriptor["clave_carpeta"], contenido_html=contenido,
                demandados=descriptor.get("demandados"),
                adjuntos_por_actuacion=adjuntos_perito,
            )
            metadatos = {
                "CAUSA": causa,
                "CLAVE_CARPETA": descriptor["clave_carpeta"],
                "DEPENDENCIA_JURISDICCIONAL": descriptor.get("dependencia"),
                "CIUDAD_CARPETA": descriptor.get("ciudad"),
                "INSTANCIA_CARPETA": descriptor.get("numero_incidente"),
            }
            for actuacion in datos.get("HISTORIAL_ACTUACIONES", []):
                actuacion.update(metadatos)
                actuacion["ORIGEN_CARPETA"] = descriptor["clave_carpeta"]
                actuacion["ORIGEN_DATA"] = datos.get("ORIGEN_DATA")
            tiene_actuaciones = bool(datos.get("HISTORIAL_ACTUACIONES"))
            inferencia_completa = bool(datos.get("ETAPA_PROCESAL") or datos.get("FASE_PROCESAL"))
            estado = "COMPLETA" if (not tiene_actuaciones or inferencia_completa) else "PARCIAL_REGISTRADA"
            resultado = {
                "version_esquema": 1,
                "estado": estado,
                "causa": causa,
                "intento_id": self._intento_actual,
                "clave_carpeta": descriptor["clave_carpeta"],
                "descriptor": descriptor,
                "firma": firma,
                "secuencia_api_inicio": secuencia_inicio,
                "secuencia_api_fin": secuencia_fin,
                "fuente": datos.get("ORIGEN_DATA"),
                "datos": datos,
                "advertencias": [],
                "error": None,
                "inicio": self._ahora_iso(),
                "duracion_s": round(monotonic() - inicio, 3),
            }
            diagnostico = {
                "url": self.page.url,
                "firma": firma,
                "intentos_navegacion_bloqueados": list(self._intentos_navegacion_bloqueados),
            }
            manifiesto = self._guardar_artefactos_carpeta(
                causa, descriptor, paquetes, contenido, frames, resultado, diagnostico
            )
            evento = "EXTRACCION_COMPLETA" if estado == "COMPLETA" else "EXTRACCION_PARCIAL_REGISTRADA"
            self._cambiar_estado_navegacion(
                causa, "EXTRACCION_EN_PROGRESO", evento, "persistir_carpeta",
                clave_carpeta=descriptor["clave_carpeta"], manifiesto=manifiesto,
                actuaciones=len(datos.get("HISTORIAL_ACTUACIONES", [])),
            )
        except Exception as exc:
            try:
                contenido, frames = self._capturar_dom_frames()
                secuencia_fin = self._secuencia_api
                paquetes = self._paquetes_ventana(secuencia_inicio, secuencia_fin, causa)
                resultado = {
                    "version_esquema": 1,
                    "estado": "ERROR_REGISTRADO",
                    "causa": causa,
                    "intento_id": self._intento_actual,
                    "clave_carpeta": descriptor["clave_carpeta"],
                    "descriptor": descriptor,
                    "datos": {"HISTORIAL_ACTUACIONES": []},
                    "advertencias": [],
                    "error": str(exc),
                    "traza": format_exc(),
                    "duracion_s": round(monotonic() - inicio, 3),
                }
                manifiesto = self._guardar_artefactos_carpeta(
                    causa, descriptor, paquetes, contenido, frames, resultado,
                    {"url": self.page.url, "error": str(exc)},
                )
                self._cambiar_estado_navegacion(
                    causa, "EXTRACCION_EN_PROGRESO", "EXTRACCION_ERROR_REGISTRADO",
                    "persistir_error_carpeta", clave_carpeta=descriptor["clave_carpeta"],
                    error=str(exc), manifiesto=manifiesto,
                )
            except Exception as error_artefactos:
                raise RuntimeError(f"ARTEFACTOS_ERROR:{error_artefactos}") from exc
        finally:
            if manifiesto:
                self._finalizar_bloqueo_navegacion(token, manifiesto)
        if not manifiesto or resultado is None:
            raise RuntimeError("RESULTADO_CARPETA_NO_DURABLE")
        resultado["manifiesto"] = manifiesto
        return resultado

    def _volver_a_movimientos(self, causa):
        self._asegurar_navegacion_permitida("volver_movimientos", causa)
        self._cambiar_estado_navegacion(
            causa, "NAVEGACION_REANUDADA", "RETORNANDO_A_MOVIMIENTOS",
            "iniciar_retorno_movimientos",
        )
        if self._ruta_es(self.page.url, "/movimientos"):
            self._cambiar_estado_navegacion(
                causa, "RETORNANDO_A_MOVIMIENTOS", "MOVIMIENTOS_CARGANDO",
                "movimientos_ya_visible",
            )
            self._esperar_movimientos_listos(causa)
            return True
        botones = self.page.locator(
            "button:has-text('Regresar'), a:has-text('Regresar'), "
            "button:has-text('Volver'), a:has-text('Volver')"
        )
        visibles = [botones.nth(i) for i in range(botones.count()) if botones.nth(i).is_visible()]
        intento_control = False
        if len(visibles) == 1:
            intento_control = True
            self._click_navegacion(visibles[0], "volver_a_movimientos")
            try:
                self.page.wait_for_url(
                    re.compile(r"/movimientos(?:[/?#]|$)"),
                    timeout=self.navegacion["movimientos_timeout_ms"],
                )
            except PlaywrightTimeoutError:
                pass
        if not self._ruta_es(self.page.url, "/movimientos"):
            if intento_control and self._ruta_es(self.page.url, "/actuaciones"):
                self._go_back_navegacion("fallback_volver_a_movimientos")
            elif not intento_control:
                self._go_back_navegacion("volver_a_movimientos_sin_control")
            self.page.wait_for_url(
                re.compile(r"/movimientos(?:[/?#]|$)"),
                timeout=self.navegacion["movimientos_timeout_ms"],
            )
        self._cambiar_estado_navegacion(
            causa, "RETORNANDO_A_MOVIMIENTOS", "MOVIMIENTOS_CARGANDO", "volver_movimientos"
        )
        self._esperar_movimientos_listos(causa)
        return True

    @staticmethod
    def _locators_visibles(locator):
        visibles = []
        for indice in range(locator.count()):
            candidato = locator.nth(indice)
            try:
                if candidato.is_visible():
                    visibles.append(candidato)
            except Exception:
                continue
        return visibles

    def _diagnosticar_buscador(self):
        """Inspecciona el buscador sin provocar navegación ni modificar la página."""
        diagnostico = {
            "url": None,
            "ruta_valida": False,
            "campos_causa": 0,
            "campo_visible": False,
            "campo_habilitado": False,
            "movimientos_visibles": False,
            "actuaciones_visibles": False,
            "carga_visible": False,
            "overlay_carga_visible": False,
            "listo": False,
        }
        if not self.page or self.page.is_closed():
            diagnostico["error"] = "PAGINA_NO_DISPONIBLE"
            return diagnostico
        diagnostico["url"] = self.page.url
        diagnostico["ruta_valida"] = self._es_buscador()
        try:
            selector_causa = (
                "input[formcontrolname='numeroCausa'], "
                "input[formcontrolname='numeroJuicio'], "
                "input[placeholder*='Dependencia' i], "
                "input[placeholder*='causa' i]"
            )
            campos = self.page.locator(selector_causa)
            diagnostico["campos_causa"] = campos.count()
            if diagnostico["campos_causa"] == 1:
                campo = campos.nth(0)
                diagnostico["campo_visible"] = bool(campo.is_visible())
                try:
                    diagnostico["campo_habilitado"] = bool(campo.is_editable())
                except Exception:
                    diagnostico["campo_habilitado"] = bool(campo.is_enabled())
            movimientos = self.page.locator(
                "app-lista-movimientos, app-movimientos, .lista-movimientos-causa"
            )
            actuaciones = self.page.locator(
                "app-actuaciones, app-informacion-proceso, .lista-actuaciones"
            )
            diagnostico["movimientos_visibles"] = bool(
                self._locators_visibles(movimientos)
            )
            diagnostico["actuaciones_visibles"] = bool(
                self._locators_visibles(actuaciones)
            )
            diagnostico["carga_visible"] = self._hay_carga_visible()
            overlay = self.page.locator(
                "div.loading-overlay[aria-busy='true'], "
                "[role='status'][aria-busy='true'].loading-overlay"
            )
            diagnostico["overlay_carga_visible"] = bool(
                self._locators_visibles(overlay)
            )
        except Exception as exc:
            diagnostico["error"] = f"DIAGNOSTICO_DOM_ERROR:{exc}"
        diagnostico["listo"] = bool(
            diagnostico["ruta_valida"]
            and diagnostico["campos_causa"] == 1
            and diagnostico["campo_visible"]
            and diagnostico["campo_habilitado"]
            and not diagnostico["movimientos_visibles"]
            and not diagnostico["actuaciones_visibles"]
            and not diagnostico["carga_visible"]
            and not diagnostico["overlay_carga_visible"]
        )
        return diagnostico

    def _esperar_buscador_listo(self, causa, timeout_ms=None):
        """Confirma por estado visible dos observaciones estables del buscador SPA."""
        timeout_ms = (
            self.navegacion["retorno_buscador_timeout_ms"]
            if timeout_ms is None else max(0, timeout_ms)
        )
        limite = monotonic() + (timeout_ms / 1000)
        consecutivas = 0
        ultimo = self._diagnosticar_buscador()
        while True:
            consecutivas = consecutivas + 1 if ultimo.get("listo") else 0
            if consecutivas >= 2:
                return ultimo
            if monotonic() >= limite:
                break
            self.page.wait_for_timeout(self.navegacion["sondeo_estabilidad_ms"])
            ultimo = self._diagnosticar_buscador()
        raise PlaywrightTimeoutError(
            "RETORNO_BUSCADOR_TIMEOUT:%s" % json.dumps(
                ultimo, ensure_ascii=False, default=str
            )
        )

    @staticmethod
    def _atributos_control_retorno(control):
        atributos = {}
        for nombre in ("id", "class", "href", "routerlink", "aria-label", "title"):
            try:
                valor = control.get_attribute(nombre)
                if valor:
                    atributos[nombre] = valor
            except Exception:
                continue
        try:
            atributos["texto"] = control.inner_text().strip()
        except Exception:
            pass
        return atributos

    def _guardar_evidencia_retorno(self, causa, contexto):
        """Guarda evidencia best-effort sin intentar una nueva navegación."""
        intento = self._clave_archivo(self._intento_actual or "sin_intento")
        directorio = os.path.join(
            "data", "temp_htmls", causa, intento, "retorno_buscador"
        )
        rutas = {}
        try:
            os.makedirs(directorio, exist_ok=True)
            ruta_json = os.path.join(directorio, "return_diagnostic.json")
            self._escribir_json_atomico(ruta_json, contexto)
            rutas["diagnostico"] = ruta_json
            ruta_html = os.path.join(directorio, "return_page.html")
            with open(ruta_html, "w", encoding="utf-8") as archivo:
                archivo.write(self.page.content())
            rutas["html"] = ruta_html
            ruta_screen = os.path.join(directorio, "return_screen.png")
            self.page.screenshot(path=ruta_screen, full_page=True)
            rutas["screenshot"] = ruta_screen
        except Exception as exc:
            contexto.setdefault("errores_evidencia", []).append(str(exc))
            logger.exception("No se pudo completar la evidencia del retorno al buscador.")
        contexto["evidencia"] = rutas
        return rutas

    def _volver_al_buscador(self, causa):
        self._asegurar_navegacion_permitida("volver_buscador", causa)
        contexto = self._retorno_buscador_actual
        if contexto is not None:
            diagnostico = self._diagnosticar_buscador()
            contexto.update({
                "diagnostico_final": diagnostico,
                "url_final": diagnostico.get("url"),
            })
            if diagnostico.get("listo"):
                contexto.update({"confirmado": True, "finalizado": True})
                return True
            raise RuntimeError("RETORNO_BUSCADOR_YA_INTENTADO")
        contexto = {
            "iniciado": True, "finalizado": False, "confirmado": False,
            "clicks": 0, "go_back": 0, "recargas": 0, "estrategia": None,
            "url_inicial": self.page.url, "url_final": self.page.url,
            "candidatos": [],
        }
        self._retorno_buscador_actual = contexto
        diagnostico = self._diagnosticar_buscador()
        contexto["diagnostico_inicial"] = diagnostico
        if diagnostico.get("listo"):
            contexto.update({
                "finalizado": True, "confirmado": True,
                "estrategia": "ya_visible", "diagnostico_final": diagnostico,
            })
            return True
        if self._es_buscador():
            contexto["estrategia"] = "ruta_busqueda_pendiente"
            try:
                diagnostico = self._esperar_buscador_listo(causa)
                contexto.update({
                    "finalizado": True,
                    "confirmado": True,
                    "url_final": diagnostico.get("url"),
                    "diagnostico_final": diagnostico,
                })
                return True
            except Exception as exc:
                diagnostico = self._diagnosticar_buscador()
                buscador_vacio = bool(
                    diagnostico.get("ruta_valida")
                    and diagnostico.get("campos_causa") == 0
                    and not diagnostico.get("movimientos_visibles")
                    and not diagnostico.get("actuaciones_visibles")
                )
                if buscador_vacio:
                    contexto.update({
                        "estrategia": "ruta_busqueda_recarga",
                        "recargas": 1,
                        "error_espera_inicial": str(exc),
                    })
                    try:
                        self._reload_navegacion(
                            "recuperar_buscador_vacio",
                            wait_until="domcontentloaded",
                            timeout=self.navegacion["retorno_buscador_timeout_ms"],
                        )
                        diagnostico = self._esperar_buscador_listo(causa)
                        contexto.update({
                            "finalizado": True,
                            "confirmado": True,
                            "url_final": diagnostico.get("url"),
                            "diagnostico_final": diagnostico,
                        })
                        return True
                    except Exception as exc_recarga:
                        contexto["error_recarga"] = str(exc_recarga)
                diagnostico = self._diagnosticar_buscador()
                contexto.update({
                    "finalizado": True,
                    "url_final": diagnostico.get("url"),
                    "diagnostico_final": diagnostico,
                    "error": f"RETORNO_BUSCADOR_FORMULARIO_NO_LISTO:{exc}",
                })
                self._guardar_evidencia_retorno(causa, contexto)
                raise RuntimeError("RETORNO_BUSCADOR_ERROR") from exc
        origen_movimientos = self._ruta_es(self.page.url, "/movimientos")
        origen_causas = self._ruta_es(self.page.url, "/causas")
        if not (origen_movimientos or origen_causas):
            contexto.update({
                "finalizado": True,
                "error": "RETORNO_BUSCADOR_ORIGEN_NO_VALIDO",
                "diagnostico_final": diagnostico,
            })
            self._guardar_evidencia_retorno(causa, contexto)
            raise RuntimeError(contexto["error"])
        controles_directos = self.page.locator(
            "a[href='/busqueda-filtros'], a[href$='/busqueda-filtros'], "
            "button[routerlink='/busqueda-filtros'], "
            "a[routerlink='/busqueda-filtros']"
        )
        directos_visibles = self._locators_visibles(controles_directos)
        if directos_visibles:
            visibles = directos_visibles
            contexto["tipo_control"] = "buscador_directo"
        else:
            botones_regreso = self.page.locator(
                "button:has-text('Regresar'), a:has-text('Regresar'), "
                "button:has-text('Nueva búsqueda'), a:has-text('Nueva búsqueda')"
            )
            visibles = self._locators_visibles(botones_regreso)
            contexto["tipo_control"] = "regreso"
        contexto["candidatos"] = [
            self._atributos_control_retorno(control) for control in visibles
        ]
        if len(visibles) == 1:
            contexto.update({"clicks": 1, "estrategia": "control"})
            try:
                self._click_navegacion(visibles[0], "volver_al_buscador")
                diagnostico = self._esperar_buscador_listo(causa)
                contexto.update({"finalizado": True, "confirmado": True,
                                 "url_final": diagnostico.get("url"),
                                 "diagnostico_final": diagnostico})
                return True
            except Exception as exc:
                contexto["error_control"] = str(exc)
                diagnostico = self._diagnosticar_buscador()
                if diagnostico.get("listo"):
                    contexto.update({"finalizado": True, "confirmado": True,
                                     "url_final": diagnostico.get("url"),
                                     "diagnostico_final": diagnostico})
                    return True
        else:
            contexto["error_control"] = "CONTROL_RETORNO_AMBIGUO_O_AUSENTE"
        if origen_movimientos and self._ruta_es(self.page.url, "/movimientos"):
            contexto.update({"go_back": 1,
                             "estrategia": "control+go_back" if contexto["clicks"] else "go_back"})
            try:
                self._go_back_navegacion("fallback_volver_al_buscador")
                diagnostico = self._esperar_buscador_listo(causa)
                contexto.update({"finalizado": True, "confirmado": True,
                                 "url_final": diagnostico.get("url"),
                                 "diagnostico_final": diagnostico})
                return True
            except Exception as exc:
                contexto["error_go_back"] = str(exc)
        diagnostico = self._diagnosticar_buscador()
        contexto.update({"finalizado": True, "url_final": diagnostico.get("url"),
                         "diagnostico_final": diagnostico,
                         "error": "RETORNO_BUSCADOR_ERROR"})
        self._guardar_evidencia_retorno(causa, contexto)
        raise RuntimeError("RETORNO_BUSCADOR_ERROR")

    def regresar_al_buscador(self):
        causa = getattr(self, "ultimo_numero_juicio", None) or "SIN_CAUSA"
        resultado = self._volver_al_buscador(self._causa_canonica(causa))
        if resultado and self.ultimo_estado_navegacion == "PREPARAR_BUSCADOR":
            self._retorno_buscador_preparacion = self._retorno_buscador_actual
            self._retorno_buscador_actual = None
        return resultado

    def _consolidar_resultados_carpetas(self, causa, resultados):
        datos = {
            "FECHA INICIO JUICIO": None,
            "FECHA INICIAL FASE ACTUAL": None,
            "ETAPA_PROCESAL": None,
            "FASE_PROCESAL": None,
            "HISTORIAL_ACTUACIONES": [],
        }
        advertencias = []
        vistos = set()
        fechas_inicio = []
        demandados_satje = []
        for resultado in resultados:
            advertencias.extend(resultado.get("advertencias", []))
            datos_carpeta = resultado.get("datos") or {}
            descriptor = resultado.get("descriptor") or {}
            if descriptor.get("demandados"):
                demandados_satje.append(descriptor["demandados"])
            fecha_inicio = (
                descriptor.get("fecha_ingreso")
                or datos_carpeta.get("FECHA INICIO JUICIO")
            )
            if fecha_inicio:
                texto_fecha = str(fecha_inicio).strip()
                for formato in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                    try:
                        fechas_inicio.append(datetime.strptime(texto_fecha, formato).date())
                        break
                    except ValueError:
                        continue
            for actuacion in datos_carpeta.get("HISTORIAL_ACTUACIONES", []):
                clave = (
                    actuacion.get("ORIGEN_CARPETA"), actuacion.get("fecha"),
                    str(actuacion.get("detalle", "")).strip().upper(),
                )
                if clave not in vistos:
                    vistos.add(clave)
                    datos["HISTORIAL_ACTUACIONES"].append(dict(actuacion))
        if datos["HISTORIAL_ACTUACIONES"]:
            self._aplicar_inferencia_consolidada(
                datos,
                causa=causa,
                demandados=demandados_satje,
                alcance="causa",
            )
        if fechas_inicio:
            datos["FECHA INICIO JUICIO"] = min(fechas_inicio).strftime("%d/%m/%Y")
        estados = [resultado.get("estado") for resultado in resultados]
        if estados and all(estado == "COMPLETA" for estado in estados):
            estado = "COMPLETADO"
        elif resultados and any(estado in {"COMPLETA", "PARCIAL_REGISTRADA"} for estado in estados):
            estado = "PARCIAL"
        else:
            estado = "EXTRACCION_ERROR"
        pertenencia = validar_pertenencia_cartera(
            datos,
            resultados,
            causa,
            self.navegacion.get("validacion_pertenencia", {}),
        )
        if pertenencia:
            estado = ESTADO_EXCLUIDO
            datos["ETAPA ACTUAL"] = ESTADO_EXCLUIDO
            datos["FASE ACTUAL"] = ESTADO_EXCLUIDO
            datos["COMENTARIO_ULTIMO"] = pertenencia["motivo"]
        enriquecer_datos_procesales(datos)
        errores = [
            resultado.get("error") for resultado in resultados if resultado.get("error")
        ]
        artefactos = [
            resultado.get("manifiesto") for resultado in resultados
            if resultado.get("manifiesto")
        ]
        return {
            "version_esquema": 1,
            "estado": estado,
            "causa": causa,
            "intento_id": self._intento_actual,
            "datos": datos,
            "carpetas": resultados,
            "resultados_carpetas": resultados,
            "carpetas_descubiertas": len(self._descriptores_actuales),
            "carpetas_completas": estados.count("COMPLETA"),
            "carpetas_parciales": estados.count("PARCIAL_REGISTRADA"),
            "carpetas_error": estados.count("ERROR_REGISTRADO"),
            "advertencias": advertencias,
            "errores": errores,
            "artefactos": artefactos,
            "error": None if estado != "EXTRACCION_ERROR" else "TODAS_LAS_CARPETAS_FALLARON",
            "pertenencia": pertenencia,
        }

    def _procesar_todas_las_carpetas(self, causa):
        self._esperar_movimientos_listos(causa)
        descriptores = self._descubrir_carpetas_procesales(causa)
        self._descriptores_actuales = list(descriptores)
        resultados = []
        for indice, descriptor in enumerate(descriptores):
            if descriptor["clave_carpeta"] in self._claves_extraidas:
                raise RuntimeError("CARPETA_DUPLICADA_EN_INTENTO")
            _, enlace = self._localizar_carpeta_procesal(causa, descriptor)
            secuencia_inicio = self._secuencia_api
            self._cambiar_estado_navegacion(
                causa, "CARPETAS_DESCUBIERTAS" if indice == 0 else "MOVIMIENTOS_LISTOS",
                "ABRIENDO_INFORMACION_PROCESO", "localizar_carpeta",
                clave_carpeta=descriptor["clave_carpeta"],
            )
            self._click_navegacion(enlace, "abrir_informacion_proceso")
            self._cambiar_estado_navegacion(
                causa, "ABRIENDO_INFORMACION_PROCESO",
                "INFORMACION_PROCESO_CARGANDO", "click_carpeta",
                clave_carpeta=descriptor["clave_carpeta"],
                secuencia_api_inicio=secuencia_inicio,
            )
            token = self._esperar_informacion_proceso_y_bloquear(
                causa, descriptor, secuencia_inicio
            )
            self._cambiar_estado_navegacion(
                causa, "NAVEGACION_BLOQUEADA", "EXTRACCION_EN_PROGRESO",
                "iniciar_extraccion", clave_carpeta=descriptor["clave_carpeta"],
                secuencia_api_inicio=secuencia_inicio,
            )
            resultado = self._extraer_informacion_proceso(
                causa, descriptor, secuencia_inicio, token
            )
            resultados.append(resultado)
            self._resultados_carpeta_actuales = list(resultados)
            self._claves_extraidas.add(descriptor["clave_carpeta"])
            self._volver_a_movimientos(causa)
        self._cambiar_estado_navegacion(
            causa, "MOVIMIENTOS_LISTOS", "CONSOLIDACION_EN_PROGRESO",
            "consolidar_carpetas", cantidad=len(resultados),
        )
        return self._consolidar_resultados_carpetas(causa, resultados)

    def _resultado_flujo(self, estado, causa, **extra):
        carpetas = list(extra.pop("carpetas", []))
        estados = [carpeta.get("estado") for carpeta in carpetas]
        error = extra.pop("error", None)
        errores = list(extra.pop("errores", []))
        if error and error not in errores:
            errores.append(error)
        return {
            "version_esquema": 1,
            "estado": estado,
            "causa": causa,
            "intento_id": self._intento_actual,
            "datos": extra.pop("datos", {}),
            "carpetas": carpetas,
            "resultados_carpetas": carpetas,
            "carpetas_descubiertas": len(self._descriptores_actuales),
            "carpetas_completas": estados.count("COMPLETA"),
            "carpetas_parciales": estados.count("PARCIAL_REGISTRADA"),
            "carpetas_error": estados.count("ERROR_REGISTRADO"),
            "advertencias": extra.pop("advertencias", []),
            "errores": errores,
            "artefactos": [
                carpeta.get("manifiesto") for carpeta in carpetas
                if carpeta.get("manifiesto")
            ],
            "error": error,
            "regreso_confirmado": extra.pop("regreso_confirmado", False),
            **extra,
        }

    def _procesar_flujo_autonomo(self, numero_juicio):
        import uuid
        causa_original = str(numero_juicio or "").strip()
        causa = self._causa_canonica(causa_original)
        self._busquedas_enviadas.clear()
        self._intento_actual = f"{causa}-{uuid.uuid4().hex[:12]}"
        self._claves_extraidas = set()
        self._resultados_carpeta_actuales = []
        self._descriptores_actuales = []
        self._intentos_navegacion_bloqueados = []
        self._retorno_buscador_actual = None
        self._retorno_buscador_preparacion = None
        self.paquetes_api_interceptados.clear()
        self._secuencia_api = 0
        self._ultima_respuesta_api_monotonic = 0.0
        self.ultimo_numero_juicio = causa
        self.ultimo_estado_navegacion = "PREPARAR_BUSCADOR"
        try:
            resultado_busqueda = self._buscar_resultado_con_reintentos(
                causa_original, causa
            )
            if resultado_busqueda == "VERIFICACION_MANUAL_SIN_RESULTADOS":
                detalle = "Verificar manualmente (La consulta no devolvi\u00f3 resultados)"
                self._cambiar_estado_navegacion(
                    causa, "VERIFICACION_MANUAL", "RETORNANDO_AL_BUSCADOR",
                    "iniciar_retorno_buscador",
                )
                regreso = self._volver_al_buscador(causa)
                self._cambiar_estado_navegacion(
                    causa, "RETORNANDO_AL_BUSCADOR", "CAUSA_ERROR",
                    "finalizar_causa_verificacion_manual",
                )
                return self._resultado_flujo(
                    "ERROR_VERIFICACION_MANUAL", causa,
                    error=detalle, regreso_confirmado=regreso,
                    requiere_reintento=False,
                    retorno_buscador=self._retorno_buscador_actual,
                )
            if resultado_busqueda == "SIN_RESULTADOS":
                self._cambiar_estado_navegacion(
                    causa, "SIN_RESULTADOS", "RETORNANDO_AL_BUSCADOR",
                    "iniciar_retorno_buscador",
                )
                regreso = self._volver_al_buscador(causa)
                self._cambiar_estado_navegacion(
                    causa, "RETORNANDO_AL_BUSCADOR", "CAUSA_SIN_RESULTADOS",
                    "finalizar_causa_sin_resultados",
                )
                return self._resultado_flujo(
                    "SIN_RESULTADOS", causa,
                    regreso_confirmado=regreso,
                    retorno_buscador=self._retorno_buscador_actual,
                )
            self._abrir_movimientos_causa(causa, resultado_busqueda)
            consolidado = self._procesar_todas_las_carpetas(causa)
            if not self._ruta_es(self.page.url, "/movimientos"):
                raise RuntimeError("CONSOLIDACION_FUERA_DE_MOVIMIENTOS")
            self._cambiar_estado_navegacion(
                causa, "CONSOLIDACION_EN_PROGRESO", "RETORNANDO_AL_BUSCADOR",
                "iniciar_retorno_buscador",
            )
            regreso = self._volver_al_buscador(causa)
            consolidado["regreso_confirmado"] = regreso
            consolidado["retorno_buscador"] = self._retorno_buscador_actual
            estado_terminal = {
                "COMPLETADO": "CAUSA_COMPLETADA",
                "PARCIAL": "CAUSA_PARCIAL",
                ESTADO_EXCLUIDO: "CAUSA_EXCLUIDA",
                "EXTRACCION_ERROR": "CAUSA_ERROR",
            }[consolidado["estado"]]
            self._cambiar_estado_navegacion(
                causa, "RETORNANDO_AL_BUSCADOR", estado_terminal, "finalizar_causa"
            )
            return consolidado
        except Exception as exc:
            logger.error("Flujo transaccional fallido para %s: %s", causa, exc, exc_info=True)
            regreso = False
            diagnostico_retorno = None
            if not (self._bloqueo_navegacion and self._bloqueo_navegacion.get("activo")):
                diagnostico_retorno = self._diagnosticar_buscador()
                regreso = bool(diagnostico_retorno.get("listo"))
                if regreso and self._retorno_buscador_actual is not None:
                    self._retorno_buscador_actual.update({
                        "finalizado": True,
                        "confirmado": True,
                        "url_final": diagnostico_retorno.get("url"),
                        "diagnostico_final": diagnostico_retorno,
                        "confirmacion_tardia": True,
                    })
                elif self._retorno_buscador_actual is None:
                    try:
                        regreso = self._volver_al_buscador(causa)
                    except Exception:
                        logger.error(
                            "No se pudo confirmar el regreso al buscador.",
                            exc_info=True,
                        )
            if self._resultados_carpeta_actuales:
                resultado = self._consolidar_resultados_carpetas(
                    causa, self._resultados_carpeta_actuales
                )
                estado_extraccion = resultado["estado"]
                descubiertas = len(self._descriptores_actuales)
                recorridas = len(self._resultados_carpeta_actuales)
                recorrido_completo = descubiertas > 0 and recorridas == descubiertas
                resultado["estado_extraccion"] = estado_extraccion
                resultado["regreso_confirmado"] = regreso
                resultado["retorno_buscador"] = self._retorno_buscador_actual
                if regreso and recorrido_completo:
                    resultado["requiere_reintento"] = False
                    resultado.setdefault("advertencias", []).append(
                        f"EXCEPCION_RECUPERADA_CON_RETORNO_CONFIRMADO:{exc}"
                    )
                    return resultado
                resultado["estado"] = "ERROR_NAVEGACION"
                resultado["requiere_reintento"] = True
                resultado["error"] = str(exc)
                resultado["errores"] = list(resultado.get("errores", [])) + [str(exc)]
                return resultado
            return self._resultado_flujo(
                "ERROR_NAVEGACION", causa, carpetas=list(self._resultados_carpeta_actuales),
                error=str(exc), regreso_confirmado=regreso,
                estado_extraccion=None,
                requiere_reintento=True,
                retorno_buscador=self._retorno_buscador_actual,
                diagnostico_retorno=diagnostico_retorno,
                navegacion_bloqueada=bool(
                    self._bloqueo_navegacion and self._bloqueo_navegacion.get("activo")
                ),
            )

    def procesar_flujo_judicatura(self, numero_juicio):
        return self._procesar_flujo_autonomo(numero_juicio)

    def extraer_detalles_juicio(self, numero_juicio=None):
        causa = numero_juicio or getattr(self, "ultimo_numero_juicio", None)
        if not causa:
            raise ValueError("NUMERO_JUICIO_REQUERIDO")
        return self._procesar_flujo_autonomo(causa)


BotJudicialLegacy = BotJudicial
BotJudicial = BotJudicialTransaccional
