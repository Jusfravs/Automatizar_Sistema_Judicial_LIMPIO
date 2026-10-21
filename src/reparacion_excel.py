"""Retira tablas sin filas de datos de un XLSX sin reescribir sus celdas."""

from __future__ import annotations

from io import BytesIO
from posixpath import join, normpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl.utils.cell import range_boundaries


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
TABLE_REL = DOC_REL + "/table"


def _tabla_sin_datos(xml: bytes) -> bool:
    tabla = ET.fromstring(xml)
    ref = tabla.get("ref")
    if not ref:
        raise ValueError("TABLA_SIN_RANGO")
    _, fila_inicial, _, fila_final = range_boundaries(ref)
    return tabla.get("headerRowCount", "1") != "0" and fila_inicial == fila_final


def _destino_tabla(rels: str, destino: str) -> str:
    if destino.startswith("/"):
        return normpath(destino.lstrip("/"))
    hoja = rels.replace("/_rels/", "/").removesuffix(".rels")
    return normpath(join(hoja.rsplit("/", 1)[0], destino))


def reparar_tablas_vacias(contenido: bytes) -> tuple[bytes, tuple[str, ...]]:
    """Devuelve un XLSX con solo sus tablas vacias eliminadas, o el original."""
    with ZipFile(BytesIO(contenido)) as origen:
        if origen.testzip() is not None:
            raise ValueError("XLSX_ZIP_INVALIDO")
        entradas = {info.filename: origen.read(info) for info in origen.infolist()}
        tablas = {
            nombre for nombre, xml in entradas.items()
            if nombre.startswith("xl/tables/") and nombre.endswith(".xml")
            and _tabla_sin_datos(xml)
        }
        if not tablas:
            return contenido, ()

        cambios: dict[str, bytes] = {}
        quitar = set(tablas)
        referenciadas: set[str] = set()
        for nombre, xml in entradas.items():
            if not nombre.startswith("xl/worksheets/_rels/") or not nombre.endswith(".rels"):
                continue
            relaciones = ET.fromstring(xml)
            ids: set[str] = set()
            for relacion in list(relaciones):
                destino = _destino_tabla(nombre, relacion.get("Target", ""))
                if relacion.get("Type") == TABLE_REL and destino in tablas:
                    ids.add(relacion.get("Id", ""))
                    referenciadas.add(destino)
                    relaciones.remove(relacion)
            if not ids:
                continue
            hoja_nombre = nombre.replace("/_rels/", "/").removesuffix(".rels")
            if hoja_nombre not in entradas:
                raise ValueError("XLSX_HOJA_FALTANTE")
            hoja = ET.fromstring(entradas[hoja_nombre])
            partes = hoja.find(f"{{{MAIN}}}tableParts")
            if partes is None:
                raise ValueError("XLSX_TABLA_SIN_REFERENCIA")
            encontrados: set[str] = set()
            for parte in list(partes):
                id_parte = parte.get(f"{{{DOC_REL}}}id")
                if id_parte in ids:
                    encontrados.add(id_parte)
                    partes.remove(parte)
            if encontrados != ids:
                raise ValueError("XLSX_RELACION_SIN_TABLA")
            if len(partes):
                partes.set("count", str(len(partes)))
            else:
                hoja.remove(partes)
            cambios[hoja_nombre] = ET.tostring(hoja, encoding="utf-8", xml_declaration=True)
            if len(relaciones):
                cambios[nombre] = ET.tostring(
                    relaciones, encoding="utf-8", xml_declaration=True
                )
            else:
                quitar.add(nombre)

        if referenciadas != tablas:
            raise ValueError("XLSX_TABLA_HUERFANA")
        tipos = ET.fromstring(entradas["[Content_Types].xml"])
        eliminados = set()
        for parte in list(tipos):
            if (parte.tag == f"{{{CONTENT}}}Override"
                    and parte.get("PartName", "").lstrip("/") in tablas):
                eliminados.add(parte.get("PartName", "").lstrip("/"))
                tipos.remove(parte)
        if eliminados != tablas:
            raise ValueError("XLSX_TIPO_TABLA_FALTANTE")
        cambios["[Content_Types].xml"] = ET.tostring(
            tipos, encoding="utf-8", xml_declaration=True
        )

        salida = BytesIO()
        from zipfile import ZIP_DEFLATED
        with ZipFile(salida, "w", compression=ZIP_DEFLATED) as destino:
            for info in origen.infolist():
                if info.filename not in quitar:
                    destino.writestr(
                        info, cambios.get(info.filename, entradas[info.filename])
                    )
    reparado = salida.getvalue()
    with ZipFile(BytesIO(reparado)) as verificacion:
        if verificacion.testzip() is not None:
            raise ValueError("XLSX_REPARADO_INVALIDO")
        if any(
            _tabla_sin_datos(verificacion.read(nombre))
            for nombre in verificacion.namelist()
            if nombre.startswith("xl/tables/") and nombre.endswith(".xml")
        ):
            raise ValueError("XLSX_TABLA_VACIA_PERSISTE")
        # Los datos y estilos se conservan: solo cambian las relaciones,
        # las hojas que contenian tableParts y el indice del paquete.
        for nombre, xml in entradas.items():
            if nombre not in quitar and nombre not in cambios:
                if verificacion.read(nombre) != xml:
                    raise ValueError("XLSX_CONTENIDO_ALTERADO")
    return reparado, tuple(sorted(tablas))
