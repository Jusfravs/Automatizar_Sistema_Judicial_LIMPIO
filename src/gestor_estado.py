import json
import os
from datetime import datetime
import pandas as pd
from src.logger_config import obtener_logger

logger = obtener_logger("GestorEstado")


def calcular_dias_fase_actual_df(df):
    """Calcula la columna DIAS EN LA FASE ACTUAL a partir de FECHA INICIAL FASE ACTUAL."""
    col_fecha = 'FECHA INICIAL FASE ACTUAL'
    col_dias = 'DIAS EN LA FASE ACTUAL'

    if col_fecha not in df.columns:
        return df

    if col_dias not in df.columns:
        df[col_dias] = None

    hoy = datetime.now()
    for idx, valor in df[col_fecha].items():
        if pd.isna(valor) or str(valor).strip() == "":
            continue

        fecha_str = str(valor).strip()
        fecha_parsed = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                fecha_parsed = datetime.strptime(fecha_str, fmt)
                break
            except ValueError:
                continue

        if fecha_parsed:
            dias = (hoy - fecha_parsed).days
            df.at[idx, col_dias] = max(0, dias)

    return df


class GestorEstado:
    """
    Gestor de Estado (Pandas): Procesa y normaliza los resultados extraídos
    hacia su formato tabular final (.csv y .xlsx).
    """
    def __init__(self):
        pass

    def generar_reporte_final(self, ruta_json="datos_extraidos.json", ruta_salida_csv="data/reporte_trabajo_final.csv"):
        """
        Lee el archivo JSON con los datos extraídos por AgenteExtractor,
        aplana la estructura usando pd.json_normalize, calcula DIAS EN LA FASE ACTUAL,
        y exporta la tabla final a CSV en UTF-8.
        """
        logger.info("Compilando reporte final desde: %s", ruta_json)
        if not os.path.exists(ruta_json):
            logger.error("No existe el archivo de resultados: %s", ruta_json)
            return None

        try:
            with open(ruta_json, "r", encoding="utf-8") as f:
                datos = json.load(f)

            if not datos:
                logger.warning("El archivo JSON está vacío. No hay datos para procesar.")
                return None

            # Aplanar estructura JSON
            df = pd.json_normalize(datos)

            # Calcular Días en la Fase Actual
            df = calcular_dias_fase_actual_df(df)

            # Reordenar columnas clave si existen
            columnas_deseadas = [
                "NUMERO_JUICIO",
                "FECHA INICIO JUICIO",
                "FECHA INICIAL FASE ACTUAL",
                "DIAS EN LA FASE ACTUAL",
                "ETAPA_PROCESAL",
                "FASE_PROCESAL",
                "HISTORIAL_ACTUACIONES"
            ]

            # Mantener columnas existentes
            columnas_presentes = [col for col in columnas_deseadas if col in df.columns]
            otras_columnas = [col for col in df.columns if col not in columnas_presentes]
            df = df[columnas_presentes + otras_columnas]

            # Limpiar valores nulos
            df = df.fillna("")

            # Convertir listas/diccionarios anidados a strings para exportación limpia en CSV
            if "HISTORIAL_ACTUACIONES" in df.columns:
                df["HISTORIAL_ACTUACIONES"] = df["HISTORIAL_ACTUACIONES"].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else str(x)
                )

            # Crear directorio de salida si no existe
            dir_salida = os.path.dirname(ruta_salida_csv)
            if dir_salida:
                os.makedirs(dir_salida, exist_ok=True)

            # Exportar a CSV UTF-8 sin índice
            df.to_csv(ruta_salida_csv, index=False, encoding="utf-8-sig")
            logger.info("Reporte final generado exitosamente en CSV: %s (%s registros)", ruta_salida_csv, len(df))

            return df

        except Exception as e:
            logger.error("Fallo al generar reporte final: %s", e)
            return None
