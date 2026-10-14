"""Comparación idempotente de dos fuentes; nunca cambia la decisión oficial."""

from __future__ import annotations

import time

from psycopg2.extras import Json

from src.catalogo_procesal import ETAPAS, FASES, enriquecer_datos_procesales, ids_para_estado
from src.historial_ia import huella_contexto, normalizar_actuaciones
from src.proveedor_nvidia import (
    ErrorAuditoriaIA, MODELO_PREDETERMINADO, VERSION_PROMPT_INFERENCIA,
    anonimizar_texto, construir_contexto_inferencia, inferir_nvidia,
    siguiente_estado_arbol,
)


COLUMNAS = (
    "numero_causa", "ejecucion_id", "huella_contexto", "modelo", "version_prompt",
    "motor_eta_actual", "motor_fas_actual", "motor_eta_ultimo", "motor_fas_ultimo",
    "ia_eta_actual", "ia_fas_actual", "ia_eta_ultimo", "ia_fas_ultimo",
    "confianza", "evidencias", "motivo", "coincide_actual", "coincide_ultimo",
    "latencia_ms", "tokens", "error",
)


def _actuaciones_identificadas(numero_causa: str, actuaciones: list[dict]) -> list[dict]:
    """Conserva IDs del archivo ya persistido; asigna IDs a capturas nuevas."""
    if actuaciones and all(
        isinstance(act, dict) and act.get("actuacion_id") for act in actuaciones
    ):
        return actuaciones
    return normalizar_actuaciones(numero_causa, actuaciones)


def huella_motor(numero_causa: str, datos: dict, actuaciones: list[dict], motor: dict) -> str:
    """Identidad estable de actuaciones y clasificación del motor."""
    ids = ids_para_estado(
        motor.get("ULTIMA_ETAPA"), motor.get("ULTIMA_FASE"),
        motor.get("ETAPA_ACTUAL") or motor.get("ULTIMA_ETAPA"),
        motor.get("FASE_ACTUAL") or motor.get("ULTIMA_FASE"),
    )
    firma = {
        **datos,
        "ULTIMA ETAPA": motor.get("ULTIMA_ETAPA"),
        "ULTIMA FASE": motor.get("ULTIMA_FASE"),
        "ETAPA ACTUAL": motor.get("ETAPA_ACTUAL") or motor.get("ULTIMA_ETAPA"),
        "FASE ACTUAL": motor.get("FASE_ACTUAL") or motor.get("ULTIMA_FASE"),
        **ids,
    }
    return huella_contexto(_actuaciones_identificadas(numero_causa, actuaciones), firma)


def comparar(
    numero_causa: str, datos: dict, actuaciones: list[dict],
    motor: dict, config_ia: dict | None = None, *, ejecucion_id=None,
) -> tuple[dict, dict | None]:
    """Devuelve registro seguro y propuesta IA; el llamador decide la jerarquía."""
    config = config_ia or {}
    modelo = config.get("modelo") or MODELO_PREDETERMINADO
    normalizadas = _actuaciones_identificadas(numero_causa, actuaciones)
    ids = ids_para_estado(
        motor.get("ULTIMA_ETAPA"), motor.get("ULTIMA_FASE"),
        motor.get("ETAPA_ACTUAL") or motor.get("ULTIMA_ETAPA"),
        motor.get("FASE_ACTUAL") or motor.get("ULTIMA_FASE"),
    )
    registro = {
        "numero_causa": numero_causa, "ejecucion_id": ejecucion_id,
        "huella_contexto": huella_motor(numero_causa, datos, actuaciones, motor),
        "modelo": modelo, "version_prompt": VERSION_PROMPT_INFERENCIA,
        "motor_eta_actual": ids["eta_id ETAPA ACTUAL"],
        "motor_fas_actual": ids["fas_id FASE ACTUAL"],
        "motor_eta_ultimo": ids["eta_id ULTIMA ETAPA"],
        "motor_fas_ultimo": ids["fas_id ULTIMA FASE"],
        "ia_eta_actual": None, "ia_fas_actual": None,
        "ia_eta_ultimo": None, "ia_fas_ultimo": None,
        "confianza": None, "evidencias": [], "motivo": None,
        "coincide_actual": None, "coincide_ultimo": None,
        "latencia_ms": None, "tokens": None, "error": None,
    }
    if not normalizadas:
        registro["error"] = "SIN_ACTUACIONES"
        return registro, None
    contexto, mapa = construir_contexto_inferencia(
        datos, normalizadas, incluir_texto=config.get("incluir_texto") is True,
    )
    inicio = time.monotonic()
    try:
        propuesta, uso = inferir_nvidia(
            contexto, mapa, modelo=modelo,
            rpm=int(config.get("rpm", 30)),
            timeout=int(config.get("timeout", 45)),
            intentos=int(config.get("intentos", 3)),
            api_key_env=config.get("api_key_env") or "NVIDIA_API_KEY",
        )
        registro["latencia_ms"] = round((time.monotonic() - inicio) * 1000)
        registro["tokens"] = uso.get("total_tokens") or (
            (uso.get("prompt_tokens") or 0) + (uso.get("completion_tokens") or 0)
        )
        registro["confianza"] = propuesta["confianza"]
        registro["evidencias"] = propuesta["evidencias"]
        registro["motivo"] = anonimizar_texto(propuesta["motivo"], datos)[:800]
        if propuesta["estado"] == "INSUFICIENTE":
            registro["error"] = "INSUFICIENTE"
        else:
            actual, hito = propuesta["estado_actual"], propuesta["ultimo_hito"]
            registro.update({
                "ia_eta_actual": actual["eta_id"], "ia_fas_actual": actual["fas_id"],
                "ia_eta_ultimo": hito["eta_id"], "ia_fas_ultimo": hito["fas_id"],
                "coincide_actual": (actual["eta_id"], actual["fas_id"]) ==
                    (registro["motor_eta_actual"], registro["motor_fas_actual"]),
                "coincide_ultimo": (hito["eta_id"], hito["fas_id"]) ==
                    (registro["motor_eta_ultimo"], registro["motor_fas_ultimo"]),
            })
        return registro, propuesta
    except ErrorAuditoriaIA as exc:
        registro["latencia_ms"] = round((time.monotonic() - inicio) * 1000)
        registro["error"] = exc.codigo
        return registro, None


def guardar_postgres(conn, registro: dict) -> bool:
    """UPSERT dentro de la transacción del llamador, sin tocar expedientes."""
    columnas = ", ".join(COLUMNAS)
    marcadores = ", ".join(["%s"] * len(COLUMNAS))
    actualizaciones = ", ".join(
        f"{campo}=EXCLUDED.{campo}" for campo in COLUMNAS
        if campo not in {"numero_causa", "huella_contexto", "modelo", "version_prompt"}
    )
    valores = [Json(registro[c]) if c == "evidencias" else registro[c] for c in COLUMNAS]
    with conn.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO inferencias_ia ({columnas}) VALUES ({marcadores}) "
            "ON CONFLICT (numero_causa, huella_contexto, modelo, version_prompt) "
            f"DO UPDATE SET {actualizaciones}, creado_en=CURRENT_TIMESTAMP",
            valores,
        )
    return True


def aplicar_jerarquia(
    datos: dict, registro: dict | None, propuesta: dict | None,
    config_ia: dict | None = None,
) -> dict:
    """Selecciona fuente; solo cambia etapas/fases cuando la IA es apta."""
    config = config_ia or {}
    if config.get("jerarquia", "motor") != "ia_primero":
        datos["FUENTE_INFERENCIA"] = "MOTOR"
        datos["MOTIVO_FUENTE"] = "JERARQUIA_MOTOR"
        return datos
    try:
        umbral = float(config.get("umbral_confianza", 0.75))
        if not 0 <= umbral <= 1:
            raise ValueError("umbral")
    except (TypeError, ValueError):
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "UMBRAL_INVALIDO"
        return datos
    error = (registro or {}).get("error")
    if error:
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = f"IA_{error}"
        return datos
    if not propuesta or propuesta.get("estado") != "OK":
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "IA_SIN_PROPUESTA"
        return datos
    if propuesta.get("requiere_revision_humana") is True:
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "IA_REQUIERE_REVISION"
        return datos
    if propuesta.get("confianza", 0) < umbral:
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "IA_BAJA_CONFIANZA"
        return datos
    actual, hito = propuesta["estado_actual"], propuesta["ultimo_hito"]
    try:
        esperado = siguiente_estado_arbol(hito)
    except ErrorAuditoriaIA:
        esperado = None
    if esperado is None or actual != esperado:
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "IA_TRANSICION_INCONSISTENTE"
        return datos
    nombres_etapa = {v: k for k, v in ETAPAS.items()}
    nombres_fase = {v: k for k, v in FASES.items()}
    try:
        etapa_actual = nombres_etapa[actual["eta_id"]]
        fase_actual = nombres_fase[actual["fas_id"]]
        ultima_etapa = nombres_etapa[hito["eta_id"]]
        ultima_fase = nombres_fase[hito["fas_id"]]
    except (KeyError, TypeError):
        datos["FUENTE_INFERENCIA"] = "MOTOR_RESPALDO"
        datos["MOTIVO_FUENTE"] = "IA_PAR_INVALIDO"
        return datos
    if (datos.get("ETAPA ACTUAL"), datos.get("FASE ACTUAL")) != (etapa_actual, fase_actual):
        datos["FECHA INICIAL FASE ACTUAL"] = None
        datos["FECHA INICIO FASE ACTUAL"] = None
    if (datos.get("ULTIMA ETAPA"), datos.get("ULTIMA FASE")) != (ultima_etapa, ultima_fase):
        datos["FECHA FIN ULTIMA FASE"] = None
    datos.update({
        "ETAPA_PROCESAL": etapa_actual, "FASE_PROCESAL": fase_actual,
        "ETAPA ACTUAL": etapa_actual, "FASE ACTUAL": fase_actual,
        "ULTIMA ETAPA": ultima_etapa, "ULTIMA FASE": ultima_fase,
        "FUENTE_INFERENCIA": "IA", "MOTIVO_FUENTE": "IA_CONFIANZA_SUFICIENTE",
    })
    enriquecer_datos_procesales(datos)
    return datos
