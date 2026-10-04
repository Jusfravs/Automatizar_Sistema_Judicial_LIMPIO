"""Cliente seguro y desacoplado para resolver reCAPTCHA v2 con 2Captcha."""

from dataclasses import dataclass
import logging
import json
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


CAMPOS_SENSIBLES = {
    "apikey", "api_key", "clientkey", "client_key", "token",
    "grecaptcharesponse", "g-recaptcha-response", "cookies",
    "authorization", "proxylogin", "proxypassword",
}


def _clave_normalizada(clave):
    return "".join(caracter for caracter in str(clave).lower() if caracter.isalnum() or caracter == "_")


def sanear_datos_captcha(valor):
    """Elimina secretos y tokens antes de auditar estructuras del proveedor."""
    if isinstance(valor, dict):
        resultado = {}
        for clave, contenido in valor.items():
            if _clave_normalizada(clave) in CAMPOS_SENSIBLES:
                resultado[clave] = "<redactado>"
            else:
                resultado[clave] = sanear_datos_captcha(contenido)
        return resultado
    if isinstance(valor, list):
        return [sanear_datos_captcha(item) for item in valor]
    if isinstance(valor, tuple):
        return tuple(sanear_datos_captcha(item) for item in valor)
    return valor


class CaptchaError(RuntimeError):
    def __init__(self, codigo, recuperable=True):
        self.codigo = str(codigo)
        self.recuperable = bool(recuperable)
        super().__init__(self.codigo)


class CaptchaConfiguracionError(CaptchaError):
    pass


class CaptchaCredencialError(CaptchaError):
    pass


class CaptchaSaldoError(CaptchaError):
    pass


class CaptchaProveedorError(CaptchaError):
    pass


class CaptchaResolucionTimeout(CaptchaError):
    pass


@dataclass(frozen=True)
class CaptchaDesafio:
    tipo: str
    website_url: str
    sitekey: str
    widget_id: str
    invisible: bool = False


@dataclass(frozen=True)
class CaptchaSolucion:
    token: str
    task_id: int
    proveedor: str
    latencia_ms: int
    costo_usd: float | None = None

    def __repr__(self):
        return (
            "CaptchaSolucion(token='<redactado>', task_id=%r, proveedor=%r, "
            "latencia_ms=%r, costo_usd=%r)"
            % (self.task_id, self.proveedor, self.latencia_ms, self.costo_usd)
        )


class TransporteJson:
    """POST JSON m??nimo basado en la biblioteca est??ndar."""

    def __call__(self, url, contenido, timeout_s):
        cuerpo = json.dumps(contenido).encode("utf-8")
        solicitud = Request(
            url,
            data=cuerpo,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(solicitud, timeout=timeout_s) as respuesta:
                if respuesta.status != 200:
                    raise CaptchaProveedorError(
                        f"CAPTCHA_HTTP_{respuesta.status}", recuperable=True
                    )
                contenido_respuesta = respuesta.read().decode("utf-8")
        except HTTPError as exc:
            raise CaptchaProveedorError(
                f"CAPTCHA_HTTP_{exc.code}", recuperable=exc.code >= 500
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CaptchaProveedorError("CAPTCHA_RED_ERROR", recuperable=True) from exc
        try:
            datos = json.loads(contenido_respuesta)
        except (TypeError, ValueError) as exc:
            raise CaptchaProveedorError(
                "CAPTCHA_RESPUESTA_NO_JSON", recuperable=True
            ) from exc
        if not isinstance(datos, dict):
            raise CaptchaProveedorError(
                "CAPTCHA_RESPUESTA_INVALIDA", recuperable=True
            )
        return datos


class Proveedor2Captcha:
    BASE_URL = "https://api.2captcha.com"
    METODOS_REINTENTABLES = frozenset({"getBalance", "getTaskResult"})
    ERRORES_CREDENCIAL = {
        "ERROR_KEY_DOES_NOT_EXIST", "ERROR_IP_NOT_ALLOWED",
        "ERROR_IP_BLOCKED", "ERROR_ACCOUNT_SUSPENDED",
    }
    ERRORES_SALDO = {"ERROR_ZERO_BALANCE"}

    def __init__(self, api_key, configuracion=None, transporte=None, dormir=None, reloj=None):
        api_key = str(api_key or "").strip()
        if not api_key:
            raise CaptchaConfiguracionError(
                "CAPTCHA_API_KEY_AUSENTE", recuperable=True
            )
        self._api_key = api_key
        self.configuracion = {
            "http_timeout_ms": 10000,
            "max_intentos_red": 3,
            "reintento_red_ms": 1000,
            "resolucion_timeout_ms": 300000,
            "sondeo_ms": 5000,
            "saldo_minimo_usd": 0.01,
        }
        self.configuracion.update(configuracion or {})
        self._transporte = transporte or TransporteJson()
        self._dormir = dormir or sleep
        self._reloj = reloj or monotonic
        self._tareas_reportadas = set()

    def _clasificar_error(self, respuesta):
        error_id = int(respuesta.get("errorId", 0) or 0)
        if error_id == 0:
            return
        codigo = str(respuesta.get("errorCode") or f"CAPTCHA_ERROR_{error_id}")
        if codigo in self.ERRORES_CREDENCIAL:
            raise CaptchaCredencialError(codigo, recuperable=False)
        if codigo in self.ERRORES_SALDO:
            raise CaptchaSaldoError(codigo, recuperable=False)
        recuperable = codigo in {"ERROR_NO_SLOT_AVAILABLE", "ERROR_CAPTCHA_UNSOLVABLE"}
        raise CaptchaProveedorError(codigo, recuperable=recuperable)

    @staticmethod
    def _es_fallo_transitorio(exc):
        codigo = str(getattr(exc, "codigo", ""))
        if codigo in {
            "CAPTCHA_RED_ERROR", "CAPTCHA_RESPUESTA_NO_JSON",
            "CAPTCHA_RESPUESTA_INVALIDA",
        }:
            return True
        if codigo.startswith("CAPTCHA_HTTP_"):
            try:
                return int(codigo.rsplit("_", 1)[-1]) >= 500
            except ValueError:
                return False
        return False

    def _solicitar(self, metodo, contenido):
        carga = {"clientKey": self._api_key, **dict(contenido or {})}
        timeout_s = max(0.1, float(self.configuracion["http_timeout_ms"]) / 1000)
        max_intentos = max(1, int(self.configuracion.get("max_intentos_red", 3)))
        if metodo not in self.METODOS_REINTENTABLES:
            max_intentos = 1

        for intento in range(1, max_intentos + 1):
            try:
                respuesta = self._transporte(
                    f"{self.BASE_URL}/{metodo}", carga, timeout_s
                )
                if not isinstance(respuesta, dict):
                    raise CaptchaProveedorError(
                        "CAPTCHA_RESPUESTA_INVALIDA", recuperable=True
                    )
                self._clasificar_error(respuesta)
                return respuesta
            except CaptchaProveedorError as exc:
                if intento >= max_intentos or not self._es_fallo_transitorio(exc):
                    raise
                espera_s = (
                    max(0, float(self.configuracion.get("reintento_red_ms", 1000)))
                    * (2 ** (intento - 1)) / 1000
                )
                logger.warning(
                    "[CAPTCHA] Fallo transitorio en %s; reintento %s/%s en %.1fs.",
                    metodo, intento + 1, max_intentos, espera_s,
                )
                self._dormir(espera_s)

    def comprobar_disponibilidad(self):
        respuesta = self._solicitar("getBalance", {})
        try:
            saldo = float(respuesta["balance"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptchaProveedorError(
                "CAPTCHA_SALDO_INVALIDO", recuperable=True
            ) from exc
        minimo = float(self.configuracion.get("saldo_minimo_usd", 0) or 0)
        if saldo < minimo:
            raise CaptchaSaldoError("CAPTCHA_SALDO_INSUFICIENTE", recuperable=False)
        return {"disponible": True, "proveedor": "2captcha", "saldo_usd": saldo}

    def resolver(self, desafio, contexto=None):
        if not isinstance(desafio, CaptchaDesafio):
            raise CaptchaConfiguracionError(
                "CAPTCHA_DESAFIO_INVALIDO", recuperable=False
            )
        inicio = self._reloj()
        respuesta = self._solicitar("createTask", {
            "task": {
                "type": "RecaptchaV2TaskProxyless",
                "websiteURL": desafio.website_url,
                "websiteKey": desafio.sitekey,
                "isInvisible": bool(desafio.invisible),
            }
        })
        try:
            task_id = int(respuesta["taskId"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptchaProveedorError(
                "CAPTCHA_TASK_ID_INVALIDO", recuperable=True
            ) from exc

        timeout_s = max(
            0.1, float(self.configuracion["resolucion_timeout_ms"]) / 1000
        )
        limite = inicio + timeout_s
        sondeo_s = max(1.0, float(self.configuracion["sondeo_ms"]) / 1000)
        intervalo_log = max(1, int(round(30 / sondeo_s)))
        sondeos = 0
        logger.info(
            "[CAPTCHA] Tarea %s creada; espera maxima del proveedor: %.0fs.",
            task_id, timeout_s,
        )
        while self._reloj() < limite:
            self._dormir(sondeo_s)
            resultado = self._solicitar("getTaskResult", {"taskId": task_id})
            estado = str(resultado.get("status") or "").lower()
            if estado == "processing":
                sondeos += 1
                if sondeos == 1 or sondeos % intervalo_log == 0:
                    logger.info(
                        "[CAPTCHA] Tarea %s sigue processing; sondeo=%s, limite=%.0fs.",
                        task_id, sondeos, timeout_s,
                    )
                continue
            if estado != "ready":
                raise CaptchaProveedorError(
                    "CAPTCHA_ESTADO_INVALIDO", recuperable=True
                )
            solucion = resultado.get("solution") or {}
            token = str(
                solucion.get("gRecaptchaResponse") or solucion.get("token") or ""
            ).strip()
            if not token:
                raise CaptchaProveedorError(
                    "CAPTCHA_TOKEN_VACIO", recuperable=True
                )
            costo = resultado.get("cost")
            try:
                costo = float(costo) if costo is not None else None
            except (TypeError, ValueError):
                costo = None
            return CaptchaSolucion(
                token=token,
                task_id=task_id,
                proveedor="2captcha",
                latencia_ms=int((self._reloj() - inicio) * 1000),
                costo_usd=costo,
            )
        raise CaptchaResolucionTimeout(
            "CAPTCHA_RESOLUCION_TIMEOUT", recuperable=True
        )

    def _reportar(self, metodo, task_id):
        task_id = int(task_id)
        if task_id in self._tareas_reportadas:
            return False
        self._solicitar(metodo, {"taskId": task_id})
        self._tareas_reportadas.add(task_id)
        return True

    def reportar_correcta(self, task_id):
        return self._reportar("reportCorrect", task_id)

    def reportar_incorrecta(self, task_id):
        return self._reportar("reportIncorrect", task_id)
