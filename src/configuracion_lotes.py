"""Compone el config común con la identidad y archivos de cada Excel."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


ARCHIVOS = {
    "archivo_origen": "origen.xlsx",
    "archivo_csv": "reporte_trabajo.csv",
    "archivo_excel_final": "reporte_final.xlsx",
    "archivo_db": "estado_local.sqlite",
    "archivo_casos_fallidos": "casos_fallidos.txt",
}


def guardar_json_atomico(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def cargar_comun(ruta: Path) -> dict:
    with Path(ruta).open(encoding="utf-8") as archivo:
        config = json.load(archivo)
    if not isinstance(config, dict) or config.get("base_de_datos", {}).get("motor") != "postgres":
        raise ValueError("CONFIG_COMUN_REQUIERE_POSTGRES")
    if "rutas" in config:
        raise ValueError("CONFIG_COMUN_NO_DEBE_TENER_RUTAS_DE_LOTE")
    return config


def leer_manifiesto(perfil: Path) -> dict:
    with (Path(perfil) / "manifiesto.json").open(encoding="utf-8") as archivo:
        manifiesto = json.load(archivo)
    if not isinstance(manifiesto, dict) or not manifiesto.get("sha256"):
        raise ValueError("MANIFIESTO_INVALIDO")
    return manifiesto


def migrar_lote_anterior(perfil: Path, base: Path) -> dict:
    """Completa lotes de la consola anterior sin reemplazar sus resultados."""
    perfil = Path(perfil).resolve()
    manifiesto = leer_manifiesto(perfil)
    csv = perfil / ARCHIVOS["archivo_csv"]
    if not csv.is_file():
        raise ValueError("LOTE_SIN_CSV")
    if manifiesto.get("version") != 2:
        antiguo = perfil / "config.json"
        if not antiguo.is_file():
            raise ValueError("LOTE_ANTERIOR_SIN_CONFIG")
        with antiguo.open(encoding="utf-8") as archivo:
            config_anterior = json.load(archivo)
        manifiesto.update({
            "version": 2,
            "perfil_id": config_anterior.get("perfil") or f"lote-{manifiesto['sha256']}",
        })
        guardar_json_atomico(perfil / "manifiesto.json", manifiesto)
    respaldo = perfil / "reporte_trabajo.csv.bak"
    if not respaldo.exists():
        shutil.copy2(csv, respaldo)
    (perfil / ARCHIVOS["archivo_casos_fallidos"]).touch(exist_ok=True)
    if not (perfil / "casos.txt").exists():
        actualizar_casos(perfil, base)
    return manifiesto


def configuracion_efectiva(perfil: Path, base: Path) -> dict:
    perfil = Path(perfil).resolve()
    manifiesto = leer_manifiesto(perfil)
    if manifiesto.get("version") != 2 or not manifiesto.get("perfil_id"):
        raise ValueError("MANIFIESTO_REQUIERE_MIGRACION")
    origen = perfil / ARCHIVOS["archivo_origen"]
    if not origen.is_file():
        raise ValueError("LOTE_SIN_EXCEL_ORIGEN")
    with origen.open("rb") as archivo:
        huella = hashlib.file_digest(archivo, "sha256").hexdigest()
    if huella != manifiesto["sha256"]:
        raise ValueError("EXCEL_ORIGEN_MODIFICADO")
    config = copy.deepcopy(cargar_comun(base))
    config["rutas"] = {campo: str(perfil / nombre) for campo, nombre in ARCHIVOS.items()}
    config["rutas"]["hoja_lectura"] = manifiesto["hoja"]
    config["perfil"] = manifiesto["perfil_id"]
    config["auditoria"] = {"total_esperado": manifiesto["filas"]}
    canonico = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    config["_config_sha256"] = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return config


def actualizar_casos(perfil: Path, base: Path) -> list[str]:
    from src.gestor_casos import GestorCasos

    config = configuracion_efectiva(perfil, base)
    gestor = GestorCasos(str(base), config_efectiva=config)
    from src.seleccion_ejecucion import _causa_comparable

    causas = []
    vistas = set()
    for causa in gestor.obtener_casos_pendientes():
        comparable = _causa_comparable(causa)
        if comparable and comparable not in vistas:
            vistas.add(comparable)
            causas.append(causa)
    ruta = Path(perfil) / "casos.txt"
    fd, temporal = tempfile.mkstemp(prefix=".casos.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            for causa in causas:
                archivo.write(f"{causa}\n")
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)
    return causas
