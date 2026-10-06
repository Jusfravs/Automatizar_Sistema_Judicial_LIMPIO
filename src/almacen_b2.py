"""Acceso privado a Backblaze B2 mediante su API compatible con S3."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse


PREFIJO_B2 = "b2:"
VARIABLES_B2 = ("B2_ENDPOINT", "B2_BUCKET", "B2_KEY_ID", "B2_APP_KEY")
MAXIMO_ENTRADA_BYTES = 20 * 1024 * 1024


def _sin_expect(request, **_):
    request.headers.pop("Expect", None)


class ClienteB2:
    def __init__(self, endpoint: str, bucket: str, key_id: str, app_key: str, *, cliente=None):
        uri = urlparse(endpoint)
        if (uri.scheme != "https" or not uri.hostname or
                not re.fullmatch(r"s3\.[a-z0-9-]+\.backblazeb2\.com", uri.hostname) or
                uri.path not in ("", "/") or uri.username or uri.password):
            raise ValueError("B2_ENDPOINT_INVALIDO")
        if not bucket or not key_id or not app_key:
            raise ValueError("B2_CONFIGURACION_INCOMPLETA")
        self.bucket = bucket
        if cliente is None:
            import boto3
            from botocore.config import Config

            cliente = boto3.client(
                "s3",
                region_name="us-east-1",
                endpoint_url=endpoint.rstrip("/"),
                aws_access_key_id=key_id,
                aws_secret_access_key=app_key,
                config=Config(
                    signature_version="s3v4", s3={"addressing_style": "path"},
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                ),
            )
            # Algunos intermediarios cierran la conexión durante el intercambio
            # Expect/100-continue. El cuerpo ya tiene longitud conocida.
            cliente.meta.events.register(
                "before-send.s3.PutObject", _sin_expect,
            )
        self.cliente = cliente

    @classmethod
    def desde_entorno(cls):
        valores = [os.environ.get(nombre, "").strip() for nombre in VARIABLES_B2]
        if not any(valores):
            return None
        if not all(valores):
            raise ValueError("B2_CONFIGURACION_INCOMPLETA")
        return cls(*valores)

    @staticmethod
    def _clave(ruta: str) -> str:
        if not ruta.startswith(PREFIJO_B2):
            raise ValueError("B2_RUTA_INVALIDA")
        clave = ruta[len(PREFIJO_B2):]
        if not clave or clave.startswith("/") or ".." in clave.split("/"):
            raise ValueError("B2_RUTA_INVALIDA")
        return clave

    def descargar(self, ruta: str) -> bytes:
        clave = self._clave(ruta)
        metadata = self.cliente.head_object(Bucket=self.bucket, Key=clave)
        if int(metadata["ContentLength"]) > MAXIMO_ENTRADA_BYTES:
            raise ValueError("EXCEL_DEMASIADO_GRANDE")
        respuesta = self.cliente.get_object(Bucket=self.bucket, Key=clave)
        return respuesta["Body"].read()

    def subir(self, ruta: str, contenido: bytes, tipo: str) -> None:
        self.cliente.put_object(
            Bucket=self.bucket, Key=self._clave(ruta), Body=contenido, ContentType=tipo,
        )
