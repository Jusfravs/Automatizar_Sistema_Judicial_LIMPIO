"""Comprueba permisos de lectura, escritura y borrado en un bucket B2 privado."""

from __future__ import annotations

import json
import uuid

from src.almacen_b2 import ClienteB2


def main() -> None:
    almacen = ClienteB2.desde_entorno()
    if almacen is None:
        raise SystemExit("B2_CONFIGURACION_INCOMPLETA")
    ruta = f"b2:pruebas-conexion/{uuid.uuid4().hex}.txt"
    contenido = b"prueba de conexion SistemaJudicial\n"
    clave = almacen._clave(ruta)
    subido = False
    try:
        almacen.subir(ruta, contenido, "text/plain")
        subido = True
        if almacen.descargar(ruta) != contenido:
            raise RuntimeError("B2_LECTURA_NO_COINCIDE")
    finally:
        if subido:
            versiones = almacen.cliente.list_object_versions(Bucket=almacen.bucket, Prefix=clave)
            if versiones.get("IsTruncated"):
                raise RuntimeError("B2_DEMASIADAS_VERSIONES")
            objetos = [
                objeto for objeto in versiones.get("Versions", []) + versiones.get("DeleteMarkers", [])
                if objeto["Key"] == clave
            ]
            if not objetos:
                raise RuntimeError("B2_VERSION_NO_ENCONTRADA")
            for objeto in objetos:
                almacen.cliente.delete_object(
                    Bucket=almacen.bucket, Key=clave, VersionId=objeto["VersionId"],
                )
    print(json.dumps({"ok": True, "lectura": True, "escritura": True, "borrado": True}))


if __name__ == "__main__":
    main()
