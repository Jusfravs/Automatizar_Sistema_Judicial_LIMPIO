"""Recalcula fases desde historiales persistidos, sin consultar el portal."""

import argparse
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.agente_extractor import MotorInferenciaProcesal
from src.catalogo_procesal import CAMPOS_ID, enriquecer_datos_procesales
from src.gestor_casos import GestorCasos
from src.validacion_pertenencia import ESTADO_EXCLUIDO, validar_pertenencia_cartera


CAMPOS_CLASIFICACION = (
    "ETAPA_PROCESAL",
    "FASE_PROCESAL",
    "FECHA INICIAL FASE ACTUAL",
    "ULTIMA ETAPA",
    "ULTIMA FASE",
    "FECHA FIN ULTIMA FASE",
    "ETAPA ACTUAL",
    "FASE ACTUAL",
    "FECHA INICIO FASE ACTUAL",
    *CAMPOS_ID,
)

CAMPOS_FECHA = {
    "FECHA INICIAL FASE ACTUAL",
    "FECHA FIN ULTIMA FASE",
    "FECHA INICIO FASE ACTUAL",
}


# Marcas creadas automaticamente por el sistema. Solo estas pueden borrarse
# durante una reclasificacion; las notas humanas se conservan.
COMENTARIOS_AUTOMATICOS_OBSOLETOS = {
    'REVISION MANUAL',
    'CASO SOLVENTADO POR REMATE',
    'CASO SOLVENTADO POR CONGELAMIENTO',
}


def _es_comentario_automatico_obsoleto(valor):
    """Distingue marcas del bot de observaciones redactadas por una persona."""
    normalizado = str(valor or "").strip().upper()
    return (
        normalizado in COMENTARIOS_AUTOMATICOS_OBSOLETOS
        or normalizado.startswith(
            "REVISION DOCUMENTAL: ESCRITO POSTERIOR SIN TIPO CONFIRMADO"
        )
    )

def _campos_desde_inferencia(inferencia):
    fecha = inferencia.get("FECHA_FIN_ULTIMA_FASE")
    fecha_fase_actual = inferencia.get("FECHA_INICIO_FASE_ACTUAL")
    campos = {
        "ETAPA_PROCESAL": (
            inferencia.get("ETAPA_ACTUAL") or inferencia.get("ULTIMA_ETAPA")
        ),
        "FASE_PROCESAL": (
            inferencia.get("FASE_ACTUAL") or inferencia.get("ULTIMA_FASE")
        ),
        "FECHA INICIAL FASE ACTUAL": fecha_fase_actual,
        "ULTIMA ETAPA": inferencia.get("ULTIMA_ETAPA"),
        "ULTIMA FASE": inferencia.get("ULTIMA_FASE"),
        "FECHA FIN ULTIMA FASE": fecha,
        "ETAPA ACTUAL": (
            inferencia.get("ETAPA_ACTUAL")
            or inferencia.get("ULTIMA_ETAPA")
        ),
        "FASE ACTUAL": (
            inferencia.get("FASE_ACTUAL")
            or inferencia.get("ULTIMA_FASE")
        ),
        "FECHA INICIO FASE ACTUAL": fecha_fase_actual,
    }
    enriquecer_datos_procesales(campos)
    return campos


def _reclasificar_datos(datos, causa=None, demandados=None):
    actuaciones = datos.get("HISTORIAL_ACTUACIONES") or []
    if not actuaciones:
        return None

    inferencia = MotorInferenciaProcesal.inferir_estado_procesal(
        actuaciones, causa=causa, demandados=demandados
    )
    if not inferencia or not inferencia.get("ULTIMA_ETAPA"):
        return None

    anteriores = {
        **{campo: datos.get(campo) for campo in CAMPOS_CLASIFICACION},
        "COMENTARIO_ULTIMO": datos.get("COMENTARIO_ULTIMO"),
    }
    nuevos = _campos_desde_inferencia(inferencia)
    datos.update(nuevos)

    mensaje = inferencia.get("MENSAJE_ESPECIAL")
    if mensaje:
        datos["COMENTARIO_ULTIMO"] = mensaje
        # La misma señal debe llegar al CSV/Excel; de otro modo SQLite y el
        # reporte final quedan con comentarios distintos.
        nuevos["COMENTARIO_ULTIMO"] = mensaje
    elif _es_comentario_automatico_obsoleto(datos.get("COMENTARIO_ULTIMO")):
        # Solo se limpia una marca automática obsoleta; comentarios detallados
        # de error y observaciones humanas permanecen intactos.
        datos["COMENTARIO_ULTIMO"] = None
        # GestorCasos usa ``None`` para no sobrescribir una celda. El texto
        # vacío sí limpia el comentario heredado en CSV y Excel.
        nuevos["COMENTARIO_ULTIMO"] = ""

    return anteriores, nuevos


def _demandados_desde_resultado(resultado):
    """Recupera los demandados de los descriptores SATJE persistidos."""
    demandados = []
    for carpeta in (
        resultado.get("resultados_carpetas")
        or resultado.get("carpetas")
        or []
    ):
        descriptor = carpeta.get("descriptor") or {}
        valor = descriptor.get("demandados")
        if valor:
            demandados.append(valor)
    return demandados


def _aplicar_validacion_pertenencia(resultado, datos, causa, configuracion):
    """Actualiza solo el estado operativo cuando SATJE confirma otra cartera."""
    pertenencia = validar_pertenencia_cartera(
        datos,
        resultado.get("resultados_carpetas") or resultado.get("carpetas") or [],
        causa,
        configuracion,
    )
    if not pertenencia:
        return None

    resultado["estado"] = ESTADO_EXCLUIDO
    resultado["pertenencia"] = pertenencia
    datos.update({
        "ETAPA ACTUAL": ESTADO_EXCLUIDO,
        "FASE ACTUAL": ESTADO_EXCLUIDO,
        "COMENTARIO_ULTIMO": pertenencia["motivo"],
    })
    return pertenencia


def _fecha_canonica(valor):
    if valor is None or str(valor).strip() == "":
        return None
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto[:10], formato).date().isoformat()
        except ValueError:
            continue
    return texto


def _campos_equivalentes(anteriores, nuevos):
    for campo in CAMPOS_CLASIFICACION:
        anterior = anteriores.get(campo)
        nuevo = nuevos.get(campo)
        if campo in CAMPOS_FECHA:
            if _fecha_canonica(anterior) != _fecha_canonica(nuevo):
                return False
        elif anterior != nuevo:
            return False
    if anteriores.get("COMENTARIO_ULTIMO") != nuevos.get("COMENTARIO_ULTIMO"):
        return False
    return True


def _reporte_tiene_revision_manual_automatica(repo, causa):
    """Detecta solo la marca automática exacta que puede quedar obsoleta."""
    if "NUMERO_JUICIO" not in repo.df.columns or "COMENTARIO_ULTIMO" not in repo.df.columns:
        return False
    causa_normalizada = _normalizar_causa(causa)
    coincidencias = repo.df[
        repo.df["NUMERO_JUICIO"].astype(str).map(_normalizar_causa)
        == causa_normalizada
    ]
    if coincidencias.empty:
        return False
    return _es_comentario_automatico_obsoleto(
        coincidencias.iloc[0]["COMENTARIO_ULTIMO"]
    )


def _ruta_configurada(config_path, valor):
    ruta = Path(valor)
    if ruta.is_absolute():
        return ruta
    return (config_path.parent / ruta).resolve()


def _respaldar_archivo(ruta, directorio, marca):
    if not ruta.exists():
        return None
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"{ruta.stem}_antes_reclasificacion_{marca}{ruta.suffix}"
    shutil.copy2(ruta, destino)
    return destino


def _respaldar_sqlite(conexion, ruta_destino):
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ruta_destino) as respaldo:
        conexion.backup(respaldo)


def _normalizar_causa(valor):
    return "".join(caracter for caracter in str(valor or "").strip() if caracter.isdigit())


def _causas_por_sucursal(repo, sucursal):
    if not sucursal:
        return None
    columna_sucursal = "SUCURSAL"
    if columna_sucursal not in repo.df.columns:
        raise KeyError("COLUMNA_SUCURSAL_AUSENTE")

    mascara = repo.df[columna_sucursal].fillna("").astype(str).str.strip().str.upper().eq(
        str(sucursal).strip().upper()
    )
    filtros = repo.config.get("filtros_activos", {})
    columna_estado = str(filtros.get("columna_estado_judicial", "")).strip().upper()
    estado = str(filtros.get("estado_judicial", "")).strip().upper()
    if columna_estado and estado and columna_estado in repo.df.columns:
        mascara &= repo.df[columna_estado].fillna("").astype(str).str.strip().str.upper().eq(estado)

    return {_normalizar_causa(causa) for causa in repo.df.loc[mascara, "NUMERO_JUICIO"] if _normalizar_causa(causa)}


def reclasificar(
    ruta_config,
    aplicar=False,
    sucursal=None,
    causas=None,
    exportar_excel=True,
    depurar_duplicados=True,
):
    config_path = Path(ruta_config).resolve()
    repo = GestorCasos(str(config_path))
    causas_alcance = _causas_por_sucursal(repo, sucursal)
    causas_solicitadas = {
        _normalizar_causa(causa) for causa in (causas or [])
        if _normalizar_causa(causa)
    }
    if causas_solicitadas:
        if causas_alcance is None:
            causas_alcance = causas_solicitadas
        else:
            causas_alcance &= causas_solicitadas
    rutas = repo.config.get("rutas", {})
    ruta_db = _ruta_configurada(
        config_path, rutas.get("archivo_db", "estado_casos.db")
    )

    conexion = sqlite3.connect(ruta_db, timeout=30.0)
    registros = conexion.execute(
        """
        SELECT r.numero_causa, r.datos_json
        FROM resultados_expediente AS r
        INNER JOIN juicios AS j ON j.numero_causa = r.numero_causa
        WHERE j.estado IN ('PROCESADO', 'PARCIAL')
        ORDER BY r.numero_causa
        """
    ).fetchall()

    cambios = []
    actualizaciones = []
    exclusiones = []
    resultados_evaluados = 0
    for causa, datos_json in registros:
        if causas_alcance is not None and _normalizar_causa(causa) not in causas_alcance:
            continue
        resultados_evaluados += 1

        resultado = json.loads(datos_json)
        datos = resultado.get("datos") or {}
        demandados = _demandados_desde_resultado(resultado)
        reclasificacion = _reclasificar_datos(
            datos, causa=causa, demandados=demandados
        )
        if reclasificacion is None:
            continue

        anteriores, nuevos = reclasificacion
        pertenencia = _aplicar_validacion_pertenencia(
            resultado,
            datos,
            causa,
            repo.config.get("navegacion", {}).get("validacion_pertenencia", {}),
        )
        estado_final = None
        if pertenencia:
            estado_final = ESTADO_EXCLUIDO
            nuevos.update({
                "ETAPA ACTUAL": ESTADO_EXCLUIDO,
                "FASE ACTUAL": ESTADO_EXCLUIDO,
                "COMENTARIO_ULTIMO": pertenencia["motivo"],
            })
            exclusiones.append({
                "causa": causa,
                "accion_detectada": pertenencia["accion_detectada"],
            })
        if (
            "COMENTARIO_ULTIMO" not in nuevos
            and nuevos.get("ETAPA ACTUAL") != "REVISION MANUAL"
            and _reporte_tiene_revision_manual_automatica(repo, causa)
        ):
            # SQLite ya no conserva esa marca, pero el reporte antiguo puede
            # tenerla. Se limpia solo el literal automático, no notas humanas.
            nuevos["COMENTARIO_ULTIMO"] = ""
        if not _campos_equivalentes(anteriores, nuevos):
            cambios.append({
                "causa": causa,
                "fase_anterior": anteriores.get("ULTIMA FASE"),
                "fase_nueva": nuevos.get("ULTIMA FASE"),
                "fecha_anterior": anteriores.get("FECHA FIN ULTIMA FASE"),
                "fecha_nueva": nuevos.get("FECHA FIN ULTIMA FASE"),
            })

        for carpeta in resultado.get("resultados_carpetas") or []:
            datos_carpeta = carpeta.get("datos") or {}
            descriptor = carpeta.get("descriptor") or {}
            _reclasificar_datos(
                datos_carpeta,
                causa=causa,
                demandados=descriptor.get("demandados"),
            )

        actualizaciones.append((
            json.dumps(resultado, ensure_ascii=False),
            causa,
            nuevos,
            estado_final,
        ))

    resumen = {
        "resultados_evaluados": resultados_evaluados,
        "clasificaciones_modificadas": len(cambios),
        "transiciones": dict(Counter(
            f"{c['fase_anterior']} -> {c['fase_nueva']}" for c in cambios
        )),
        "cambios": cambios,
        "exclusiones": exclusiones,
    }
    if sucursal:
        resumen["sucursal"] = str(sucursal).strip().upper()
    if causas_solicitadas:
        resumen["causas_solicitadas"] = sorted(causas_solicitadas)

    if not aplicar:
        resumen["filas_duplicadas_exactas_eliminadas"] = 0
        conexion.close()
        return resumen

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    directorio_backup = Path(repo.ruta_final).resolve().parent / "backups"
    _respaldar_sqlite(
        conexion,
        directorio_backup / f"{ruta_db.stem}_antes_reclasificacion_{marca}.db",
    )
    _respaldar_archivo(Path(repo.ruta_csv), directorio_backup, marca)
    _respaldar_archivo(Path(repo.ruta_final), directorio_backup, marca)

    try:
        conexion.execute("BEGIN IMMEDIATE")
        for datos_json, causa, nuevos, estado_final in actualizaciones:
            conexion.execute(
                """
                UPDATE resultados_expediente
                SET datos_json = ?, actualizado_en = CURRENT_TIMESTAMP
                WHERE numero_causa = ?
                """,
                (datos_json, causa),
            )
            if estado_final:
                conexion.execute(
                    "UPDATE juicios SET estado = ? WHERE numero_causa = ?",
                    (estado_final, causa),
                )
            if not repo.actualizar_caso(causa, nuevos):
                raise LookupError(f"CAUSA_NO_ENCONTRADA_EN_CSV:{causa}")

        # No se elimina una causa repetida si representa otra cartera, usuario
        # o crÃ©dito. La depuraciÃ³n solo toca copias idÃ©nticas en todas las
        # columnas, despuÃ©s de actualizar su clasificaciÃ³n.
        filas_duplicadas_eliminadas = (
            repo.depurar_filas_duplicadas_exactas()
            if depurar_duplicados else 0
        )
        if not repo.guardar():
            raise RuntimeError("PERSISTENCIA_ERROR:CSV")
        if exportar_excel:
            repo.exportar_excel()
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()

    resumen["aplicado"] = True
    resumen["filas_duplicadas_exactas_eliminadas"] = filas_duplicadas_eliminadas
    resumen["ruta_excel"] = (
        str(Path(repo.ruta_final).resolve()) if exportar_excel else None
    )
    resumen["directorio_backups"] = str(directorio_backup.resolve())
    return resumen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--sucursal")
    parser.add_argument("--causa", action="append", dest="causas")
    parser.add_argument("--sin-excel", action="store_true")
    parser.add_argument("--sin-depurar", action="store_true")
    argumentos = parser.parse_args()
    print(json.dumps(
        reclasificar(
            argumentos.config,
            aplicar=argumentos.aplicar,
            sucursal=argumentos.sucursal,
            causas=argumentos.causas,
            exportar_excel=not argumentos.sin_excel,
            depurar_duplicados=not argumentos.sin_depurar,
        ),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
