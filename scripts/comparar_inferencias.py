"""Resume comparaciones motor–IA y evalúa etiquetas humanas seudónimas.

Requiere INFERENCIA_REPORTE_SAL en el entorno para generar IDs estables.
Nunca escribe números de causa, nombres, motivos ni texto judicial en las salidas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import statistics
from collections import Counter
from pathlib import Path

from src.catalogo_procesal import ETAPAS, FASES
from src.proveedor_nvidia import MODELO_PREDETERMINADO, VERSION_PROMPT_INFERENCIA
from src.repositorio_postgres import RepositorioColaPostgres


CAMPOS_CSV = (
    "id_seudonimo", "motor_eta_actual", "motor_fas_actual",
    "motor_eta_ultimo", "motor_fas_ultimo", "ia_eta_actual", "ia_fas_actual",
    "ia_eta_ultimo", "ia_fas_ultimo", "coincide_actual", "coincide_ultimo",
    "confianza", "latencia_ms", "tokens", "error",
)
CAMPOS_ETIQUETA = (
    "id_seudonimo", "eta_id_actual_correcta", "fas_id_actual_correcta",
    "eta_id_ultimo_correcta", "fas_id_ultimo_correcta", "evidencia",
    "confianza", "revisor", "fecha_corte", "estrato",
)


def seudonimo(numero_causa: str, sal: bytes) -> str:
    if len(sal) < 16:
        raise ValueError("SAL_DE_REPORTE_DEMASIADO_CORTA")
    return hmac.new(sal, numero_causa.encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def _par(fila: dict, fuente: str, momento: str) -> tuple[int | None, int | None]:
    return fila.get(f"{fuente}_eta_{momento}"), fila.get(f"{fuente}_fas_{momento}")


def evaluar(filas: list[dict], etiquetas: dict[str, dict]) -> dict:
    """Calcula acuerdos y exactitud sin tratar al motor como verdad."""
    disponibles = [f for f in filas if f.get("ia_eta_actual") is not None]
    errores_api = [f for f in filas if f.get("error") not in (None, "", "INSUFICIENTE")]
    latencias = sorted(int(f["latencia_ms"]) for f in filas if f.get("latencia_ms") is not None)
    desacuerdos = Counter()
    nombres_etapa = {v: k for k, v in ETAPAS.items()}
    for fila in disponibles:
        if _par(fila, "motor", "actual") != _par(fila, "ia", "actual"):
            desacuerdos[nombres_etapa.get(fila.get("motor_eta_actual"), "SIN ETAPA")] += 1
    metricas = {
        "total": len(filas), "comparables": len(disponibles),
        "acuerdo_actual": sum(_par(f, "motor", "actual") == _par(f, "ia", "actual") for f in disponibles),
        "acuerdo_ultimo": sum(_par(f, "motor", "ultimo") == _par(f, "ia", "ultimo") for f in disponibles),
        "insuficientes": sum(f.get("error") == "INSUFICIENTE" for f in filas),
        "errores_api": len(errores_api), "errores_por_codigo": dict(Counter(f["error"] for f in errores_api)),
        "desacuerdos_por_etapa": dict(desacuerdos),
        "latencia_media_ms": round(statistics.mean(latencias)) if latencias else None,
        "latencia_p95_ms": latencias[min(len(latencias) - 1, int(len(latencias) * .95))] if latencias else None,
        "tokens_total": sum(int(f.get("tokens") or 0) for f in filas),
        "etiquetadas": 0,
    }
    for fuente in ("motor", "ia"):
        metricas[fuente] = {
            "etapa_actual_correcta": 0, "fase_actual_correcta": 0,
            "par_actual_correcto": 0, "par_ultimo_correcto": 0,
            "falsos_avances_actual": 0, "evaluables": 0,
        }
    fases_validas = set(FASES.values())
    for fila in filas:
        verdad = etiquetas.get(fila["id_seudonimo"])
        if not verdad:
            continue
        try:
            eta = int(verdad["eta_id_actual_correcta"])
            fas = int(verdad["fas_id_actual_correcta"])
            eta_ult = int(verdad["eta_id_ultimo_correcta"])
            fas_ult = int(verdad["fas_id_ultimo_correcta"])
        except (ValueError, TypeError, KeyError):
            continue
        if eta not in ETAPAS.values() or eta_ult not in ETAPAS.values() or fas not in fases_validas or fas_ult not in fases_validas:
            continue
        metricas["etiquetadas"] += 1
        for fuente in ("motor", "ia"):
            f_eta, f_fas = _par(fila, fuente, "actual")
            f_eta_ult, f_fas_ult = _par(fila, fuente, "ultimo")
            if f_eta is None or f_fas is None:
                continue
            m = metricas[fuente]
            m["evaluables"] += 1
            m["etapa_actual_correcta"] += int(f_eta == eta)
            m["fase_actual_correcta"] += int(f_fas == fas)
            m["par_actual_correcto"] += int((f_eta, f_fas) == (eta, fas))
            m["par_ultimo_correcto"] += int((f_eta_ult, f_fas_ult) == (eta_ult, fas_ult))
            m["falsos_avances_actual"] += int(f_fas > fas)
    return metricas


def leer_etiquetas(ruta: Path | None) -> dict[str, dict]:
    if ruta is None or not ruta.exists():
        return {}
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        return {f["id_seudonimo"]: f for f in csv.DictReader(archivo)
                if f.get("id_seudonimo")}


def _porcentaje(n: int, total: int) -> str:
    return f"{100 * n / total:.1f} %" if total else "sin muestra"


def redactar_reporte(m: dict) -> str:
    lineas = [
        "# Comparación de inferencia dual", "",
        f"Comparaciones registradas: **{m['total']}**; pares comparables: **{m['comparables']}**.",
        "",
        "## Acuerdo motor–IA", "",
        f"- Estado actual: {_porcentaje(m['acuerdo_actual'], m['comparables'])}.",
        f"- Último hito: {_porcentaje(m['acuerdo_ultimo'], m['comparables'])}.",
        f"- Respuestas insuficientes: {m['insuficientes']}.",
        "- Desacuerdos por etapa del motor: " +
        (", ".join(f"{k}: {v}" for k, v in sorted(m["desacuerdos_por_etapa"].items())) or "ninguno") + ".",
        "", "## API NVIDIA", "",
        f"- Errores: {m['errores_api']} de {m['total']} ({_porcentaje(m['errores_api'], m['total'])}).",
        f"- Códigos: {', '.join(f'{k}: {v}' for k, v in sorted(m['errores_por_codigo'].items())) or 'ninguno'}.",
        f"- Latencia media/p95: {m['latencia_media_ms']} / {m['latencia_p95_ms']} ms.",
        f"- Tokens totales: {m['tokens_total']}.",
        "", "## Etiquetas humanas", "",
        f"Causas etiquetadas y válidas: **{m['etiquetadas']}** (meta inicial: unas 100, estratificadas).",
    ]
    for fuente in ("motor", "ia"):
        x = m[fuente]
        lineas.extend([
            f"### {fuente.upper()}", "",
            f"- Exactitud de etapa actual: {_porcentaje(x['etapa_actual_correcta'], x['evaluables'])}.",
            f"- Exactitud de fase actual: {_porcentaje(x['fase_actual_correcta'], x['evaluables'])}.",
            f"- Par actual correcto: {_porcentaje(x['par_actual_correcto'], x['evaluables'])}.",
            f"- Par del último hito correcto: {_porcentaje(x['par_ultimo_correcto'], x['evaluables'])}.",
            f"- Falsos avances actuales: {x['falsos_avances_actual']} de {x['evaluables']}.", "",
        ])
    lineas.extend([
        "## Decisión pendiente", "",
        "Criterio propuesto: IA al menos igual al motor en etapa **y** fase actuales, "
        "falsos avances no mayores y errores API inferiores a 5 %. Justin confirma "
        "la jerarquía tras revisar la muestra etiquetada. Con cero etiquetas no se "
        "puede decidir la superioridad de ninguna fuente.", "",
        "El CSV contiene solo IDs seudónimos y métricas. La clave HMAC se conserva "
        "fuera del repositorio; sin ella no puede reproducirse la correspondencia.", "",
    ])
    return "\n".join(lineas)


def ejecutar(config_ruta: Path, salida_md: Path, salida_csv: Path,
            etiquetas_ruta: Path | None = None) -> dict:
    sal = os.environ.get("INFERENCIA_REPORTE_SAL", "").encode("utf-8")
    if len(sal) < 16:
        raise ValueError("INFERENCIA_REPORTE_SAL_AUSENTE_O_CORTA")
    config = json.loads(config_ruta.read_text(encoding="utf-8-sig"))
    if config.get("base_de_datos", {}).get("motor") != "postgres":
        raise ValueError("REPORTE_REQUIERE_POSTGRES")
    modelo = (config.get("inferencia_ia") or {}).get("modelo") or MODELO_PREDETERMINADO
    repo = RepositorioColaPostgres.desde_config(config["base_de_datos"])
    conn = repo._get_connection()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (numero_causa)
                    numero_causa, motor_eta_actual, motor_fas_actual,
                    motor_eta_ultimo, motor_fas_ultimo, ia_eta_actual,
                    ia_fas_actual, ia_eta_ultimo, ia_fas_ultimo,
                    coincide_actual, coincide_ultimo, confianza,
                    latencia_ms, tokens, error
                FROM inferencias_ia
                WHERE modelo=%s AND version_prompt=%s
                ORDER BY numero_causa, creado_en DESC, id DESC
            """, (modelo, VERSION_PROMPT_INFERENCIA))
            nombres = [c.name for c in cur.description]
            filas = [dict(zip(nombres, fila)) for fila in cur.fetchall()]
    finally:
        conn.close()
    for fila in filas:
        fila["id_seudonimo"] = seudonimo(fila.pop("numero_causa"), sal)
    metricas = evaluar(filas, leer_etiquetas(etiquetas_ruta))
    salida_md.parent.mkdir(parents=True, exist_ok=True)
    salida_csv.parent.mkdir(parents=True, exist_ok=True)
    salida_md.write_text(redactar_reporte(metricas), encoding="utf-8")
    with salida_csv.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)
    return {"comparaciones": metricas["total"], "etiquetadas": metricas["etiquetadas"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--reporte", type=Path, default=Path("reporte_inferencia_dual.md"))
    parser.add_argument("--csv", type=Path, default=Path("reporte_inferencia_dual.csv"))
    parser.add_argument("--etiquetas", type=Path)
    args = parser.parse_args()
    print(json.dumps(ejecutar(args.config, args.reporte, args.csv, args.etiquetas)))


if __name__ == "__main__":
    main()
