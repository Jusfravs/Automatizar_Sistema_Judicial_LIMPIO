"""Procesamiento de una causa sin conocer la persistencia ni los reportes."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.ejecucion import ResultadoCaso
from src.logger_config import obtener_logger
from src.motor_busqueda_web import BotJudicial


logger = obtener_logger("ProcesadorCaso")


def motivo_revision_manual_por_formato(causa):
    texto = str(causa or "").strip()
    if re.fullmatch(r"\d{5}-\d{4}-\d{4,5}", texto):
        return None
    if re.fullmatch(r"\d{13,14}", texto):
        return None
    return "FORMATO_CAUSA_INVALIDO"


def estado_terminal_para_resultado(estado):
    return {
        "COMPLETADO": "PROCESADO",
        "PARCIAL": "PARCIAL",
        "SIN_RESULTADOS": "SIN_RESULTADOS",
        "EXCLUIDO_NO_CORRESPONDE": "EXCLUIDO_NO_CORRESPONDE",
        "ERROR_VERIFICACION_MANUAL": "REVISION",
    }.get(str(estado or ""))


def resultado_es_recuperable(estado, error=None):
    if "ARTEFACTOS_ERROR:[WinError 206]" in str(error or ""):
        return False
    return str(estado or "") in {
        "EXTRACCION_ERROR",
        "ERROR_NAVEGACION",
        "ERROR",
    }


class ProcesadorCaso:
    """Mantiene una sesion de navegador acotada y produce resultados puros."""

    def __init__(
        self,
        url_portal: str,
        navegacion: Mapping[str, Any] | None,
        captcha: Mapping[str, Any] | None,
        navegador_visible: bool = True,
        casos_por_sesion: int = 10,
    ):
        self.url_portal = url_portal
        self.navegacion = dict(navegacion or {})
        self.captcha = dict(captcha or {})
        self.navegador_visible = bool(navegador_visible)
        self.casos_por_sesion = int(casos_por_sesion)
        self._bot = None
        self._casos_sesion = 0

    def _asegurar_navegador(self):
        if self._bot is None:
            self._bot = BotJudicial(
                self.url_portal,
                self.navegacion,
                captcha=self.captcha,
            )
            self._bot.iniciar_navegador(modo_visible=self.navegador_visible)
            self._casos_sesion = 0
        return self._bot

    def cerrar(self):
        if self._bot is not None:
            try:
                self._bot.cerrar_navegador()
            finally:
                self._bot = None
                self._casos_sesion = 0

    def procesar(self, numero_causa):
        causa = str(numero_causa or "").strip()
        motivo_formato = motivo_revision_manual_por_formato(causa)
        if motivo_formato:
            datos = {
                "COMENTARIO_ULTIMO": "REVISION MANUAL: %s" % motivo_formato,
                "ETAPA ACTUAL": "REVISION MANUAL",
                "FASE ACTUAL": "REVISION MANUAL",
            }
            return ResultadoCaso(
                numero_causa=causa,
                estado="ERROR_VERIFICACION_MANUAL",
                datos=datos,
                error=motivo_formato,
                regreso_confirmado=True,
                resultado_original={"estado": "ERROR_VERIFICACION_MANUAL"},
            )

        try:
            bot = self._asegurar_navegador()
            resultado = bot.procesar_flujo_judicatura(causa)
            if not isinstance(resultado, dict) or not resultado.get("estado"):
                raise RuntimeError("CONTRATO_RESULTADO_INVALIDO")
            resultado = dict(resultado)
            estado = resultado["estado"]
            datos = dict(resultado.get("datos") or {})
            error = resultado.get("error")

            if estado == "SIN_RESULTADOS":
                datos.setdefault(
                    "COMENTARIO_ULTIMO",
                    "REVISION MANUAL: Verificar manualmente "
                    "(La consulta no devolvio resultados)",
                )
                resultado["datos"] = datos
            elif estado in {"ERROR_NAVEGACION", "ERROR_VERIFICACION_MANUAL"}:
                detalle = error or estado
                datos.setdefault("COMENTARIO_ULTIMO", "REVISION MANUAL: %s" % detalle)
                datos.setdefault("ETAPA ACTUAL", "REVISION MANUAL")
                datos.setdefault("FASE ACTUAL", "REVISION MANUAL")
                resultado["datos"] = datos

            estados_conocidos = {
                "COMPLETADO",
                "PARCIAL",
                "EXCLUIDO_NO_CORRESPONDE",
                "SIN_RESULTADOS",
                "EXTRACCION_ERROR",
                "ERROR_NAVEGACION",
                "ERROR_VERIFICACION_MANUAL",
            }
            if estado not in estados_conocidos:
                raise RuntimeError("ESTADO_RESULTADO_DESCONOCIDO:%s" % estado)

            self._casos_sesion += 1
            if estado == "ERROR_NAVEGACION" or not resultado.get(
                "regreso_confirmado", False
            ):
                if estado not in {
                    "EXTRACCION_ERROR",
                    "ERROR_NAVEGACION",
                    "ERROR_VERIFICACION_MANUAL",
                }:
                    raise RuntimeError("REGRESO_AL_BUSCADOR_NO_CONFIRMADO")
                self.cerrar()
            elif self._casos_sesion >= self.casos_por_sesion:
                self.cerrar()

            return ResultadoCaso(
                numero_causa=causa,
                estado=estado,
                datos=datos,
                error=error,
                origen="ESATJE_TRANSACCIONAL",
                regreso_confirmado=bool(resultado.get("regreso_confirmado")),
                resultado_original=resultado,
            )
        except Exception as exc:
            logger.exception("Fallo procesando la causa %s", causa)
            self.cerrar()
            detalle = "EXCEPCION_NO_CONTROLADA:%s:%s" % (
                type(exc).__name__,
                str(exc) or "SIN_DETALLE",
            )
            return ResultadoCaso(
                numero_causa=causa,
                estado="EXTRACCION_ERROR",
                error=detalle,
                regreso_confirmado=False,
                resultado_original={
                    "estado": "EXTRACCION_ERROR",
                    "error": detalle,
                    "regreso_confirmado": False,
                },
            )
