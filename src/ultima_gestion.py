"""Derivacion auditable de la ultima gestion registrada en SATJE."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, MutableMapping


CAMPO_FECHA_ULTIMA_GESTION = "FECHA ULTIMA GESTION JUDICIAL"
CAMPO_ESTADO_ULTIMA_GESTION = "ESTADO ULTIMA GESTION JUDICIAL"
MARCA_REVISION_ULTIMA_GESTION = "REVISIÓN MANUAL"
MOTIVO_REVISION_ULTIMA_GESTION = "TITULO_ULTIMA_GESTION_NO_VERIFICABLE"

_ZONA_GUAYAQUIL = timezone(timedelta(hours=-5))

_CAMPOS_TITULO = (
    "titulo",
    "titulo_original",
    "actuacion",
    "tipoActuacion",
    "actividad",
)
_FECHA_DIA_MES_ANIO = re.compile(r"^\s*\d{2}/\d{2}/\d{4}\s*$")
_ETIQUETA_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def _historial_como_lista(valor: Any) -> list[Mapping[str, Any]]:
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            valor = json.loads(texto)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(valor, list):
        return []
    return [item for item in valor if isinstance(item, Mapping)]


def _fecha_ordenable(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return _fecha_local(valor)
    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto:
        return None
    for formato in (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(texto[:19], formato)
        except ValueError:
            continue
    try:
        return _fecha_local(datetime.fromisoformat(texto.replace("Z", "+00:00")))
    except ValueError:
        return None


def _fecha_local(valor: datetime) -> datetime:
    if valor.tzinfo is not None:
        return valor.astimezone(_ZONA_GUAYAQUIL).replace(tzinfo=None)
    return valor


def _es_titulo_breve(valor: str) -> bool:
    return (
        bool(valor)
        and len(valor) <= 160
        and not any(caracter in valor for caracter in "\r\n")
        and not _ETIQUETA_HTML.search(valor)
    )


def _titulo_explicito(actuacion: Mapping[str, Any]) -> str | None:
    for campo in _CAMPOS_TITULO:
        valor = actuacion.get(campo)
        if valor is not None and str(valor).strip():
            titulo = str(valor).strip()
            if _es_titulo_breve(titulo):
                return titulo
    return None


def _titulo_legacy(actuacion: Mapping[str, Any]) -> str | None:
    """Reconoce las filas resumen históricas sin confundirlas con el HTML."""
    fecha = str(actuacion.get("fecha") or "")
    detalle = actuacion.get("detalle")
    if (
        not _FECHA_DIA_MES_ANIO.fullmatch(fecha)
        or detalle is None
        or not str(detalle).strip()
    ):
        return None
    titulo = str(detalle).strip()
    if not _es_titulo_breve(titulo):
        return None
    return titulo


def obtener_ultima_gestion_judicial(historial: Any) -> tuple[str | None, str | None]:
    """Devuelve fecha y titulo literal de la gestion mas reciente.

    SATJE entrega en el mismo historial el contenido completo de providencias y
    las filas resumen del listado. Primero se identifica el dia cronologicamente
    mas reciente y, dentro de ese dia, se prioriza el titulo explicito de la fila
    resumen. Para historiales anteriores a este cambio se reconoce como resumen
    la actuacion con fecha ``dd/mm/aaaa`` y detalle sin HTML.
    """
    candidatas = []
    for posicion, actuacion in enumerate(_historial_como_lista(historial)):
        fecha = _fecha_ordenable(actuacion.get("fecha"))
        if fecha is not None:
            candidatas.append((posicion, fecha, actuacion))
    if not candidatas:
        return None, None

    dia_mas_reciente = max(fecha.date() for _, fecha, _ in candidatas)
    del_dia = [
        (posicion, fecha, actuacion)
        for posicion, fecha, actuacion in candidatas
        if fecha.date() == dia_mas_reciente
    ]

    for extractor_titulo in (_titulo_explicito, _titulo_legacy):
        for _, _, actuacion in del_dia:
            titulo = extractor_titulo(actuacion)
            if titulo:
                return dia_mas_reciente.strftime("%d/%m/%Y"), titulo

    # Si solo hay cuerpo de providencia, se requiere una verificacion humana.
    return dia_mas_reciente.strftime("%d/%m/%Y"), MARCA_REVISION_ULTIMA_GESTION


def enriquecer_ultima_gestion_judicial(
    datos: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Agrega los dos campos derivados sin intervenir en la inferencia."""
    historial = datos.get("HISTORIAL_ACTUACIONES")
    fecha, titulo = obtener_ultima_gestion_judicial(historial)
    if titulo is None and historial:
        titulo = MARCA_REVISION_ULTIMA_GESTION
    if fecha is not None:
        datos[CAMPO_FECHA_ULTIMA_GESTION] = fecha
    if titulo is not None:
        datos[CAMPO_ESTADO_ULTIMA_GESTION] = titulo
    return datos
