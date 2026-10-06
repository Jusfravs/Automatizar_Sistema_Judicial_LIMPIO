"""Comprueba una clave NVIDIA NIM sin enviar datos judiciales ni mostrarla."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELO = "nvidia/nemotron-3-super-120b-a12b"


def main() -> int:
    clave = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not clave:
        print(json.dumps({"ok": False, "motivo": "NVIDIA_API_KEY_AUSENTE"}))
        return 2

    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": "Responde solamente OK."}],
        "max_tokens": 32,
        "temperature": 0,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    solicitud = Request(
        URL,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {clave}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(solicitud, timeout=40) as respuesta:
            datos = json.load(respuesta)
            if not datos.get("choices"):
                print(json.dumps({"ok": False, "http": respuesta.status, "motivo": "RESPUESTA_SIN_CHOICES"}))
                return 1
            print(json.dumps({"ok": True, "http": respuesta.status, "modelo": MODELO}))
            return 0
    except HTTPError as error:
        print(json.dumps({"ok": False, "http": error.code, "motivo": "NVIDIA_RECHAZO_SOLICITUD"}))
    except (URLError, TimeoutError) as error:
        print(json.dumps({"ok": False, "motivo": type(error).__name__}))
    except (ValueError, TypeError) as error:
        print(json.dumps({"ok": False, "motivo": type(error).__name__}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
