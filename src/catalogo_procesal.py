"""Catálogo oficial de etapas y fases para integración con Sistemas.

Esta capa traduce el resultado del motor de inferencia a identificadores. No
contiene palabras clave ni participa en la selección de actuaciones.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping


ETAPAS = {
    "1 PRESENTACION Y CALIFICACION": 10,
    "2 CITACION": 11,
    "3 CONTESTACION": 12,
    "4 AUDIENCIA": 13,
    "5 SENTENCIA": 14,
    "6 LIQUIDACION Y EMBARGO": 15,
}

FASES = {
    "1.1 PRESENTAR DEMANDA": 77,
    "1.2 ACLARAR Y/O COMPLETAR DEMANDA": 78,
    "1.3 CALIFICACION": 79,
    "2.1 CITACION": 80,
    "2.2 CITACION POR PRENSA": 81,
    "3.1 CONTESTACION": 82,
    "4.1 FIJACION FECHA AUDIENCIA": 83,
    "4.2 AUDIENCIA": 84,
    "5.1 SENTENCIA EMITIDA POR EL JUEZ": 85,
    "5.2 APELACION": 86,
    "5.3 SENTENCIA EJECUTORIADA": 87,
    "6.1 LIQUIDACION PERITO LIQUIDADOR": 88,
    "6.2 MANDAMIENTO DE EJECUCION": 89,
    "6.3 EMBARGO": 90,
    "6.4 REMATE": 91,
    "6.5 CONGELAMIENTO DE CUENTAS": 92,
}

ALIAS_ETAPAS = {
    "CONTESTACION": "3 CONTESTACION",
}

ALIAS_FASES = {
    "1.2 COMPLETAR/ACLARAR DEMANDA": "1.2 ACLARAR Y/O COMPLETAR DEMANDA",
    "2.1 CITACION (PERSONA/BOLETA)": "2.1 CITACION",
    "CONTESTACION": "3.1 CONTESTACION",
    "4.2 AUDIENCIA / ACTA RESUMEN": "4.2 AUDIENCIA",
    "6.5 CONGELAMIENTO DE CUENTAS / CIERRE": "6.5 CONGELAMIENTO DE CUENTAS",
}

CAMPOS_ID = (
    "eta_id ULTIMA ETAPA",
    "fas_id ULTIMA FASE",
    "eta_id ETAPA ACTUAL",
    "fas_id FASE ACTUAL",
)


def _texto(valor: Any) -> str:
    return str(valor or "").strip().upper()


def canonicalizar_etapa(valor: Any) -> Any:
    """Devuelve la etiqueta oficial cuando existe; conserva desconocidos."""
    clave = _texto(valor)
    if not clave:
        return valor
    return ALIAS_ETAPAS.get(clave, clave)


def canonicalizar_fase(valor: Any) -> Any:
    """Devuelve la etiqueta oficial cuando existe; conserva desconocidos."""
    clave = _texto(valor)
    if not clave:
        return valor
    return ALIAS_FASES.get(clave, clave)


def id_etapa(valor: Any) -> int | None:
    return ETAPAS.get(canonicalizar_etapa(valor))


def id_fase(valor: Any) -> int | None:
    return FASES.get(canonicalizar_fase(valor))


def ids_para_estado(
    ultima_etapa: Any,
    ultima_fase: Any,
    etapa_actual: Any,
    fase_actual: Any,
) -> dict[str, int | None]:
    return {
        "eta_id ULTIMA ETAPA": id_etapa(ultima_etapa),
        "fas_id ULTIMA FASE": id_fase(ultima_fase),
        "eta_id ETAPA ACTUAL": id_etapa(etapa_actual),
        "fas_id FASE ACTUAL": id_fase(fase_actual),
    }


def enriquecer_datos_procesales(
    datos: MutableMapping[str, Any], *, normalizar_etiquetas: bool = False
) -> MutableMapping[str, Any]:
    """Agrega los cuatro IDs a un payload ya clasificado.

    ``normalizar_etiquetas`` se usa en contratos externos. El motor puede
    conservar sus nombres históricos para garantizar retrocompatibilidad.
    """
    ultima_etapa = datos.get("ULTIMA ETAPA") or datos.get("ETAPA_PROCESAL")
    ultima_fase = datos.get("ULTIMA FASE") or datos.get("FASE_PROCESAL")
    etapa_actual = datos.get("ETAPA ACTUAL") or datos.get("ETAPA_PROCESAL")
    fase_actual = datos.get("FASE ACTUAL") or datos.get("FASE_PROCESAL")

    if normalizar_etiquetas:
        for campo, normalizador in (
            ("ULTIMA ETAPA", canonicalizar_etapa),
            ("ULTIMA FASE", canonicalizar_fase),
            ("ETAPA ACTUAL", canonicalizar_etapa),
            ("FASE ACTUAL", canonicalizar_fase),
        ):
            if campo in datos and datos[campo] not in (None, ""):
                datos[campo] = normalizador(datos[campo])

    datos.update(
        ids_para_estado(ultima_etapa, ultima_fase, etapa_actual, fase_actual)
    )
    return datos


def validar_ids(datos: Mapping[str, Any]) -> bool:
    """Indica si los IDs presentes coinciden con sus etiquetas."""
    esperados = ids_para_estado(
        datos.get("ULTIMA ETAPA"),
        datos.get("ULTIMA FASE"),
        datos.get("ETAPA ACTUAL"),
        datos.get("FASE ACTUAL"),
    )
    return all(datos.get(campo) == valor for campo, valor in esperados.items())
