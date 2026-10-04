"""Validación conservadora de pertenencia de un expediente a una cartera."""

import re
from html import unescape

from src.agente_extractor import normalizar_texto


ESTADO_EXCLUIDO = "EXCLUIDO_NO_CORRESPONDE"
POLITICA_PREDETERMINADA = {
    "activa": True,
    "actores_requeridos": ["FUNDACION PAREA EL DESARROLLO INTEGRAL ESPOIR"],
    "acciones_requeridas": ["COBRO DE PAGARE A LA ORDEN"],
}


def _normalizar(valor):
    texto = re.sub(r"<[^>]+>", " ", str(valor or ""))
    return re.sub(r"\s+", " ", normalizar_texto(unescape(texto))).strip()


def _causa_canonica(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _lista_configuracion(configuracion, clave):
    valor = (configuracion or {}).get(clave, [])
    if isinstance(valor, str):
        valor = [valor]
    return [_normalizar(item) for item in valor if _normalizar(item)]


def _accion_de_caratula(texto, causa):
    """Extrae una acción solo desde una carátula inequívoca de la causa."""
    causa_canonica = _causa_canonica(causa)
    if len(causa_canonica) not in (13, 14):
        return None
    patron_causa = re.compile(
        rf"{causa_canonica[:5]}\s*-?\s*{causa_canonica[5:9]}\s*-?\s*"
        rf"{causa_canonica[9:]}"
    )
    if not patron_causa.search(texto):
        return None
    if "DATOS DEL EXPEDIENTE" not in texto:
        return None
    coincidencia = re.search(
        r"\bACCION\s*:\s*(.+?)(?=\b(?:ESTADO DEL PROCESO|DATOS DEL ACTOR|"
        r"TIPO DE PROCESO|MATERIA)\b|$)",
        texto,
    )
    return coincidencia.group(1).strip(" .;:-") if coincidencia else None


def validar_pertenencia_cartera(datos, resultados_carpetas, causa, configuracion):
    """Devuelve evidencia de exclusión o ``None`` cuando no hay certeza suficiente.

    No descarta expedientes por ausencia de información. Solo excluye si una
    carátula del mismo SATJE ofrece una acción explícita no permitida y ningún
    actor requerido aparece en los datos obtenidos.
    """
    configuracion_efectiva = dict(POLITICA_PREDETERMINADA)
    configuracion_efectiva.update(configuracion or {})
    if not configuracion_efectiva.get("activa", False):
        return None

    actores_requeridos = _lista_configuracion(configuracion_efectiva, "actores_requeridos")
    acciones_requeridas = _lista_configuracion(configuracion_efectiva, "acciones_requeridas")
    if not actores_requeridos or not acciones_requeridas:
        return None

    textos = []
    for carpeta in resultados_carpetas or []:
        descriptor = carpeta.get("descriptor") or {}
        textos.extend((descriptor.get("actores"), descriptor.get("demandados")))
    textos.extend(
        actuacion.get("detalle", "")
        for actuacion in (datos or {}).get("HISTORIAL_ACTUACIONES", [])
    )
    textos_normalizados = [_normalizar(texto) for texto in textos if texto]
    evidencia_unida = " ".join(textos_normalizados)

    if any(actor in evidencia_unida for actor in actores_requeridos):
        return None

    acciones = [
        accion
        for texto in textos_normalizados
        if (accion := _accion_de_caratula(texto, causa))
    ]
    if not acciones:
        return None

    accion = acciones[0]
    if any(permitida in accion for permitida in acciones_requeridas):
        return None

    return {
        "estado": ESTADO_EXCLUIDO,
        "causa": _causa_canonica(causa),
        "accion_detectada": accion,
        "actores_requeridos": actores_requeridos,
        "motivo": (
            f"{ESTADO_EXCLUIDO}: acción SATJE '{accion}' no corresponde a la cartera"
        ),
    }
