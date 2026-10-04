"""Lectura cronológica consultiva sobre señales del árbol procesal existente.

No clasifica oficialmente un caso: ordena hallazgos para auditoría y señala
menciones históricas, ambigüedades y posibles regresiones.
"""

from __future__ import annotations

from src.agente_extractor import MotorInferenciaProcesal
from src.catalogo_procesal import canonicalizar_fase, id_etapa, id_fase


VERSION_TEMPORAL = "temporal-1"
EXCEPCIONES = {"NULIDAD", "REVOCATORIA", "REAPERTURA", "REMISION", "CAMBIO DE INSTANCIA"}


def reconstruir_cronologia(cronologia: list[dict]) -> dict:
    """Conserva solo avances respaldados por una señal de fase no ambigua."""
    taxonomia = MotorInferenciaProcesal.TAXONOMIA_COMPLETA
    fases_ordenadas = [canonicalizar_fase(fase) for fase in MotorInferenciaProcesal.ORDEN_FASES]
    rangos = {fase: indice for indice, fase in enumerate(fases_ordenadas)}
    terminos_por_fase = {}
    etapa_por_fase = {}
    for etapa, fase, terminos in taxonomia:
        fase_canonica = canonicalizar_fase(fase)
        terminos_por_fase.setdefault(fase_canonica, set()).update(
            str(termino).strip().upper() for termino in terminos
        )
        etapa_por_fase[fase_canonica] = etapa

    hitos = []
    historicas = []
    ambiguas = []
    regresiones = []
    rango_vigente = -1
    for actuacion in cronologia:
        senales = set(actuacion.get("senales") or [])
        candidatas = [
            fase for fase, terminos in terminos_por_fase.items()
            if senales.intersection(terminos)
        ]
        referencia = actuacion.get("ref")
        if len(candidatas) > 1:
            ambiguas.append({"ref": referencia, "fases": candidatas})
            continue
        if not candidatas:
            continue
        fase = candidatas[0]
        rango = rangos.get(fase)
        if rango is None:
            ambiguas.append({"ref": referencia, "fases": [fase], "motivo": "SIN_ORDEN"})
            continue
        hito = {
            "ref": referencia, "fecha": actuacion.get("fecha"),
            "eta_id": id_etapa(etapa_por_fase[fase]), "fas_id": id_fase(fase),
            "fase": fase,
        }
        if hito["eta_id"] is None or hito["fas_id"] is None:
            ambiguas.append({"ref": referencia, "fases": [fase], "motivo": "ID_NO_CATALOGADO"})
            continue
        if rango < rango_vigente:
            if EXCEPCIONES.intersection(actuacion.get("tipo") or []):
                regresiones.append(hito)
            else:
                historicas.append(hito)
            continue
        if rango > rango_vigente:
            hitos.append(hito)
            rango_vigente = rango

    siguiente = None
    if 0 <= rango_vigente < len(fases_ordenadas) - 1:
        fase = fases_ordenadas[rango_vigente + 1]
        siguiente = {"fase": fase, "fas_id": id_fase(fase)}
    return {
        "version": VERSION_TEMPORAL,
        "hitos_candidatos": hitos,
        "ultimo_hito_candidato": hitos[-1] if hitos else None,
        "siguiente_fase_esperada": siguiente,
        "menciones_historicas": historicas[-20:],
        "ambiguedades": ambiguas[-20:],
        "regresiones_posibles": regresiones[-20:],
    }
