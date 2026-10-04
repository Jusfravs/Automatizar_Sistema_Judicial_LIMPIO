"""Crea desde cero el entorno regional de Quito, sin muestreo ni resultados previos."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd


RAIZ_PREDETERMINADA = Path(__file__).resolve().parents[1]
CONFIG_RELATIVA = Path("config_quito.json")
SUCURSAL = "QUITO"
OFICINA = "QUITO SUR"
ESTADO_JUDICIAL = "ACTIVO"
HOJA = "QUITO"

COLUMNAS_REGIONALES = (
    ("CODIGO_JUICIO", "CODIGO_JUICIO"),
    ("SUCURSAL", "SUCURSAL"),
    ("OFICINA", "OFICINA"),
    ("ASESOR", "ASESOR"),
    ("USUARIO", "USUARIO"),
    ("CREDITO", "CREDITO"),
    ("CEDULA_IDENTIDAD", "CEDULA_IDENTIDAD"),
    # Igual que el archivo regional de Santo Domingo: ESTADO representa el
    # estado judicial y no el estado comercial del Excel maestro.
    ("ESTADO", "ESTADO.1"),
    ("SEGMENTO", "SEGMENTO"),
    ("NOMBRES_CLIENTE", "NOMBRES_CLIENTE"),
    ("NOMBRE", "NOMBRE"),
    ("SALDO_CAPITAL", "SALDO_CAPITAL"),
    ("SALDO_TOTAL", "SALDO_TOTAL"),
    ("SALDO_CLIENTE_GRUPO", "SALDO_CLIENTE_GRUPO"),
    ("PRODUCTO", "PRODUCTO"),
    ("NUMERO_JUICIO", "NUMERO_JUICIO"),
    ("JUZGADO", "JUZGADO"),
    ("CUANTIA", "CUANTIA"),
    ("DIAS_MORA", "DIAS_MORA"),
    ("CODIGO_ETAPA", "CODIGO_ETAPA"),
    ("ETAPA_PROCESAL", "ETAPA_PROCESAL (ACTUAL)"),
    ("CODIGO_FASE", "CODIGO_FASE"),
    ("FASE_PROCESAL", "FASE_PROCESAL (ACTUAL)"),
    ("FECHA_INICIO", "FECHA_INICIO"),
    ("FECHA_ULTIMA_GESTION_JUDICIAL", "FECHA_ULTIMA_GESTION_JUDICIAL"),
    ("FECHA_ULTIMO_COMPROMISO", "FECHA_ULTIMO_COMPROMISO"),
    ("VALOR_ULTIMO_COMPROMISO", "VALOR_ULTIMO_COMPROMISO"),
    ("RECUPERACION_ACTUAL", "RECUPERACION_ACTUAL"),
    ("RECUPERACION_MES_ANTERIOR", "RECUPERACION_MES_ANTERIOR"),
    ("SISTEMA", "SISTEMA"),
    ("COMENTARIO_ULTIMO", "COMENTARIO_ULTIMO"),
)


def _ruta_segura(raiz: Path, valor: str) -> Path:
    ruta = (raiz / valor).resolve()
    try:
        ruta.relative_to(raiz)
    except ValueError as exc:
        raise ValueError(f"RUTA_FUERA_DEL_PROYECTO:{ruta}") from exc
    return ruta


def _cargar_json(ruta: Path) -> dict:
    with ruta.open("r", encoding="utf-8") as archivo:
        return json.load(archivo)


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    copia = df.copy()
    copia.columns = copia.columns.astype(str).str.strip().str.upper()
    return copia


def _construir_reporte_regional(df_maestro: pd.DataFrame) -> pd.DataFrame:
    requeridas = {origen for _, origen in COLUMNAS_REGIONALES}
    faltantes = sorted(requeridas - set(df_maestro.columns))
    if faltantes:
        raise KeyError(f"COLUMNAS_REQUERIDAS_AUSENTES:{','.join(faltantes)}")

    def normalizada(columna: str) -> pd.Series:
        return (
            df_maestro[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    mascara = (
        normalizada("SUCURSAL").eq(SUCURSAL)
        & normalizada("OFICINA").eq(OFICINA)
        & normalizada("ESTADO.1").eq(ESTADO_JUDICIAL)
    )
    filtrado = df_maestro.loc[mascara]
    regional = pd.DataFrame(
        {destino: filtrado[origen].copy() for destino, origen in COLUMNAS_REGIONALES}
    )
    regional["NUMERO_JUICIO"] = (
        regional["NUMERO_JUICIO"]
        .astype(str)
        .str.strip()
        .str.replace("/", "-", regex=False)
    )
    return regional


def _validar_alcance(df: pd.DataFrame, config: dict) -> tuple[list[str], dict]:
    auditoria = config.get("auditoria", {})
    filas_esperadas = int(auditoria["total_esperado"])
    causas_esperadas = int(auditoria["total_causas_unicas_esperado"])
    causas = list(dict.fromkeys(df["NUMERO_JUICIO"].tolist()))

    if df["NUMERO_JUICIO"].eq("").any():
        raise ValueError("NUMERO_JUICIO_VACIO")
    if len(df) != filas_esperadas:
        raise ValueError(
            f"TOTAL_FILAS_INESPERADO:esperado={filas_esperadas}:real={len(df)}"
        )
    if len(causas) != causas_esperadas:
        raise ValueError(
            "TOTAL_CAUSAS_UNICAS_INESPERADO:"
            f"esperado={causas_esperadas}:real={len(causas)}"
        )
    if set(df["ESTADO"].astype(str).str.strip().str.upper()) != {ESTADO_JUDICIAL}:
        raise ValueError("ESTADO_JUDICIAL_REGIONAL_INVALIDO")

    return causas, {
        "filas": len(df),
        "causas_unicas": len(causas),
        "duplicados_por_causa": int(df["NUMERO_JUICIO"].duplicated().sum()),
        "estado_inicial": "PENDIENTE",
        "resultados_migrados": 0,
    }


def _crear_sqlite_vacio(raiz: Path, ruta_db: Path, causas: list[str]) -> dict:
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    from src.gestor_cola import GestorCola

    temporal = ruta_db.with_name(ruta_db.name + ".nuevo")
    if temporal.exists():
        temporal.unlink()
    cola = GestorCola(ruta_db=str(temporal))
    cola.poblar_cola(causas)

    import sqlite3

    with closing(sqlite3.connect(temporal)) as conexion:
        estados = dict(
            conexion.execute(
                "SELECT estado, COUNT(*) FROM juicios GROUP BY estado"
            ).fetchall()
        )
        resultados = conexion.execute(
            "SELECT COUNT(*) FROM resultados_expediente"
        ).fetchone()[0]
        eventos = conexion.execute(
            "SELECT COUNT(*) FROM eventos_extraccion"
        ).fetchone()[0]

    esperado = {"PENDIENTE": len(causas)}
    if estados != esperado or resultados != 0 or eventos != 0:
        temporal.unlink(missing_ok=True)
        raise ValueError(
            f"SQLITE_NO_ESTA_VACIO:estados={estados}:"
            f"resultados={resultados}:eventos={eventos}"
        )
    temporal.replace(ruta_db)
    return {"estados": estados, "resultados": resultados, "eventos": eventos}


def preparar(raiz: Path) -> dict:
    raiz = raiz.resolve()
    config = _cargar_json(raiz / CONFIG_RELATIVA)
    config_general = _cargar_json(raiz / "config.json")
    rutas = config["rutas"]

    ruta_csv = _ruta_segura(raiz, rutas["archivo_csv"])
    ruta_origen = _ruta_segura(raiz, rutas["archivo_origen"])
    ruta_final = _ruta_segura(raiz, rutas["archivo_excel_final"])
    ruta_db = _ruta_segura(raiz, rutas["archivo_db"])
    ruta_fallidos = _ruta_segura(raiz, rutas["archivo_casos_fallidos"])
    ruta_origen.parent.mkdir(parents=True, exist_ok=True)

    salidas = (ruta_csv, ruta_origen, ruta_final, ruta_db, ruta_fallidos)
    existentes = [str(ruta) for ruta in salidas if ruta.exists()]
    if existentes:
        raise FileExistsError("ENTORNO_QUITO_NO_ESTA_VACIO:" + "|".join(existentes))

    ruta_maestra = _ruta_segura(
        raiz, config_general["rutas"]["archivo_origen"]
    )
    hoja_maestra = config_general["rutas"].get("hoja_lectura", "migrado")
    df_maestro = _normalizar_columnas(
        pd.read_excel(ruta_maestra, sheet_name=hoja_maestra)
    )
    df_quito = _construir_reporte_regional(df_maestro)
    causas, alcance = _validar_alcance(df_quito, config)

    df_quito.to_excel(ruta_origen, index=False, sheet_name=HOJA)
    df_quito.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    sqlite = _crear_sqlite_vacio(raiz, ruta_db, causas)
    ruta_fallidos.write_text("", encoding="utf-8")

    from src.gestor_casos import GestorCasos

    repo = GestorCasos(str(raiz / CONFIG_RELATIVA))
    repo.exportar_excel()

    return {
        "config": str((raiz / CONFIG_RELATIVA).resolve()),
        "alcance": alcance,
        "sqlite": sqlite,
        "archivos": {clave: str(_ruta_segura(raiz, valor)) for clave, valor in rutas.items() if clave.startswith("archivo_")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea desde cero todos los casos activos de Quito."
    )
    parser.add_argument("--proyecto", type=Path, default=RAIZ_PREDETERMINADA)
    args = parser.parse_args()
    print(json.dumps(preparar(args.proyecto), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
