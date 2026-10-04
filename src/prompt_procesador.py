# src/prompt_procesador.py
import json
import os
import re
from src.logger_config import obtener_logger

logger = obtener_logger("PromptProcesador")

RUTA_PROMPT_DEFAULT = "Prompt_correcion_Filtro.txt"


def cargar_plantilla_prompt(ruta_prompt=RUTA_PROMPT_DEFAULT):
    """Carga la plantilla de prompt desde el sistema de archivos."""
    if not os.path.exists(ruta_prompt):
        raise FileNotFoundError(f"No se encontró el archivo de plantilla prompt en: {ruta_prompt}")

    with open(ruta_prompt, "r", encoding="utf-8") as f:
        return f.read()


def construir_prompt(
    causa_id: str,
    texto_extraido: str,
    numero_actual: int = 1,
    total_causas: int = 1,
    ruta_prompt: str = RUTA_PROMPT_DEFAULT,
) -> str:
    """
    Construye el prompt completo reemplazando los marcadores de posición dinámicos de forma segura.
    """
    plantilla = cargar_plantilla_prompt(ruta_prompt)
    prompt_construido = (
        plantilla.replace("{causa_id}", str(causa_id))
        .replace("{texto_extraido_del_expediente}", str(texto_extraido or "SIN CONTENIDO DISPONIBLE"))
        .replace("{numero_actual}", str(numero_actual))
        .replace("{total_causas}", str(total_causas))
    )
    return prompt_construido


def limpiar_y_validar_json(respuesta_raw: str, causa_id: str = None) -> dict:
    """
    Limpia cualquier delimitador Markdown de la respuesta del LLM y la parsea como JSON estructurado.
    Si el JSON es inválido o incompleto, retorna un fallback seguro con requiere_revision_humana=True.
    """
    if not respuesta_raw:
        return _generar_fallback(causa_id, "Respuesta vacía recibida del LLM.")

    # Remover bloques Markdown (```json ... ```) si el modelo los incluyó por error
    limpio = re.sub(r"^```(?:json)?\s*", "", respuesta_raw.strip(), flags=re.IGNORECASE)
    limpio = re.sub(r"\s*```$", "", limpio, flags=re.IGNORECASE).strip()

    try:
        data = json.loads(limpio)
        if not isinstance(data, dict):
            return _generar_fallback(causa_id, "El formato retornado no es un objeto JSON.")

        # Validar y asegurar campos requeridos para la base de datos
        data.setdefault("numero_causa", causa_id or "DESCONOCIDO")
        data.setdefault("etapa_procesal_detectada", "Indeterminada")
        data.setdefault("fase_procesal_detectada", "Indeterminada")
        data.setdefault("fecha_ultimo_movimiento", None)
        data.setdefault("resumen_ultimo_movimiento", "Sin síntesis procesal.")
        data.setdefault("requiere_revision_humana", False)
        data.setdefault("unidad_judicial", "Indeterminada")

        if not isinstance(data.get("actores"), dict):
            data["actores"] = {"demandante": "Indeterminado", "demandado": "Indeterminado"}

        return data

    except json.JSONDecodeError as e:
        logger.error("Error al decodificar JSON retornado por LLM: %s. Raw content: %s", e, respuesta_raw[:200])
        return _generar_fallback(causa_id, f"JSONDecodeError: {e}")


def _generar_fallback(causa_id: str, motivo: str) -> dict:
    """Genera un diccionario estructurado de respaldo para no interrumpir el flujo."""
    return {
        "numero_causa": causa_id or "DESCONOCIDO",
        "etapa_procesal_detectada": "Indeterminada",
        "fase_procesal_detectada": "Indeterminada",
        "fecha_ultimo_movimiento": None,
        "resumen_ultimo_movimiento": f"Revisión requerida por error de parsing: {motivo}",
        "requiere_revision_humana": True,
        "unidad_judicial": "Indeterminada",
        "actores": {
            "demandante": "Indeterminado",
            "demandado": "Indeterminado"
        }
    }
