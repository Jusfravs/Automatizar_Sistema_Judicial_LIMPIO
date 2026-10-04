"""Prepara un Excel externo para el contrato de GestorCasos sin inferencia judicial."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd


ALIAS = {
    "NUMERO DE JUICIO": "NUMERO_JUICIO",
    "NUMERO JUICIO": "NUMERO_JUICIO",
    "NUMERO DE CAUSA": "NUMERO_JUICIO",
    "NUMERO CAUSA": "NUMERO_JUICIO",
    "CODIGO DE JUICIO": "CODIGO_JUICIO",
    "CODIGO JUICIO": "CODIGO_JUICIO",
}
REQUERIDAS = {"CODIGO_JUICIO", "NUMERO_JUICIO", "SUCURSAL", "ESTADO"}


def _cabecera(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto.strip().upper())
    return ALIAS.get(texto, texto)


def _identificador(valor: object) -> str:
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def leer_y_validar(ruta: Path, hoja: str | None = None) -> tuple[pd.DataFrame, dict]:
    ruta = Path(ruta).expanduser().resolve()
    if not ruta.is_file() or ruta.suffix.lower() != ".xlsx":
        raise ValueError(f"EXCEL_XLSX_NO_ENCONTRADO:{ruta}")

    with pd.ExcelFile(ruta) as libro:
        candidatas = [hoja] if hoja else [s for s in ("Reporte", "migrado") if s in libro.sheet_names]
        if not candidatas:
            candidatas = libro.sheet_names
        if hoja and hoja not in libro.sheet_names:
            raise ValueError(f"HOJA_NO_ENCONTRADA:{hoja}")

        datos = None
        seleccion = None
        for nombre in candidatas:
            for encabezado in (0, 1, 5):
                muestra = pd.read_excel(libro, sheet_name=nombre, header=encabezado, nrows=0)
                nombres = [_cabecera(c) for c in muestra.columns]
                if REQUERIDAS.issubset(nombres) or (
                    {"CODIGO_JUICIO", "NUMERO_JUICIO", "SUCURSAL", "ESTADO.1"}.issubset(nombres)
                ):
                    datos = pd.read_excel(libro, sheet_name=nombre, header=encabezado, dtype=object)
                    seleccion = (nombre, encabezado)
                    break
            if datos is not None:
                break
    if datos is None:
        raise ValueError("CABECERA_NO_RECONOCIDA: se requieren CODIGO_JUICIO, NUMERO_JUICIO, SUCURSAL y ESTADO")

    datos.columns = [_cabecera(c) for c in datos.columns]
    if len(datos.columns) != len(set(datos.columns)):
        raise ValueError("COLUMNAS_DUPLICADAS_TRAS_NORMALIZAR")
    # En el maestro, ESTADO.1 es el estado judicial; ESTADO suele ser comercial.
    if "ESTADO.1" in datos.columns:
        datos["ESTADO"] = datos["ESTADO.1"]
    for campo in ("CODIGO_JUICIO", "NUMERO_JUICIO"):
        datos[campo] = datos[campo].map(_identificador)
    datos["NUMERO_JUICIO"] = datos["NUMERO_JUICIO"].str.replace("/", "-", regex=False)
    datos["ESTADO"] = datos["ESTADO"].fillna("").astype(str).str.strip().str.upper()
    if datos.empty:
        raise ValueError("EXCEL_SIN_FILAS")
    if datos["CODIGO_JUICIO"].eq("").any():
        raise ValueError("CODIGO_JUICIO_VACIO")
    if datos["CODIGO_JUICIO"].duplicated().any():
        raise ValueError("CODIGO_JUICIO_DUPLICADO")
    if datos["NUMERO_JUICIO"].eq("").any():
        raise ValueError("NUMERO_JUICIO_VACIO")
    if datos["SUCURSAL"].isna().any() or datos["SUCURSAL"].astype(str).str.strip().eq("").any():
        raise ValueError("SUCURSAL_VACIA")
    if datos["ESTADO"].eq("").any():
        raise ValueError("ESTADO_JUDICIAL_VACIO")

    with ruta.open("rb") as archivo:
        huella = hashlib.file_digest(archivo, "sha256").hexdigest()
    resumen = {
        "hoja": seleccion[0],
        "fila_encabezado": seleccion[1] + 1,
        "filas": len(datos),
        "causas_unicas": datos["NUMERO_JUICIO"].nunique(),
        "activas": int(datos["ESTADO"].eq("ACTIVO").sum()),
        "sha256": huella,
    }
    return datos, resumen
