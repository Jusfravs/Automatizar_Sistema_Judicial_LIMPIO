"""Comprueba B2 y muestra solo etapa/código HTTP, nunca credenciales."""

from __future__ import annotations

import json
import uuid

from src.almacen_b2 import ClienteB2


def _resumen_error(etapa: str, error: Exception) -> dict:
    respuesta = getattr(error, "response", {})
    if not isinstance(respuesta, dict):
        respuesta = {}
    detalle = respuesta.get("Error", {})
    metadata = respuesta.get("ResponseMetadata", {})
    return {
        "ok": False,
        "etapa": etapa,
        "codigo": detalle.get("Code") or type(error).__name__,
        "http": metadata.get("HTTPStatusCode"),
    }


def main() -> int:
    etapa = "configuracion"
    try:
        almacen = ClienteB2.desde_entorno()
        if almacen is None:
            raise ValueError("B2_CONFIGURACION_INCOMPLETA")
    except Exception as error:
        print(json.dumps(_resumen_error(etapa, error)))
        return 1

    ruta = f"b2:pruebas-conexion/{uuid.uuid4().hex}.txt"
    contenido = b"prueba de conexion SistemaJudicial\n"
    clave = almacen._clave(ruta)
    subido = False
    fallo = None
    try:
        etapa = "subida"
        almacen.subir(ruta, contenido, "text/plain")
        subido = True
        etapa = "lectura"
        if almacen.descargar(ruta) != contenido:
            raise RuntimeError("B2_LECTURA_NO_COINCIDE")
    except Exception as error:
        fallo = _resumen_error(etapa, error)

    if subido:
        try:
            etapa = "listado_de_versiones"
            versiones = almacen.cliente.list_object_versions(Bucket=almacen.bucket, Prefix=clave)
            if versiones.get("IsTruncated"):
                raise RuntimeError("B2_DEMASIADAS_VERSIONES")
            objetos = [
                objeto for objeto in versiones.get("Versions", []) + versiones.get("DeleteMarkers", [])
                if objeto["Key"] == clave
            ]
            if not objetos:
                raise RuntimeError("B2_VERSION_NO_ENCONTRADA")
            etapa = "borrado"
            for objeto in objetos:
                almacen.cliente.delete_object(
                    Bucket=almacen.bucket, Key=clave, VersionId=objeto["VersionId"],
                )
        except Exception as error:
            if fallo is None:
                fallo = _resumen_error(etapa, error)

    if fallo:
        print(json.dumps(fallo))
        return 1
    print(json.dumps({"ok": True, "lectura": True, "escritura": True, "borrado": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
