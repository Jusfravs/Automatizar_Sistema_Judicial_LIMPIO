"""Comprobacion de solo lectura del motor del portal; nunca imprime credenciales."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def comprobar(ruta_config: Path) -> dict:
    from consola import _repositorio, diagnostico
    from src.configuracion_lotes import cargar_comun
    from src.servicio_portal import RepositorioSolicitudes

    estado = {
        "configuracion": False,
        "postgres": False,
        "esquema": False,
        "tabla_lotes": False,
        "storage": False,
        "captcha": False,
        "nvidia": bool(os.environ.get("NVIDIA_API_KEY")),
        "ultimo_lote_finalizado": None,
    }
    try:
        config = cargar_comun(ruta_config)
        estado["configuracion"] = True
        revision = diagnostico(config)
        estado["postgres"] = bool(revision["conexion"])
        estado["esquema"] = bool(revision["esquema_completo"] and revision["auditoria_config"])
        if estado["postgres"]:
            repo = _repositorio(config)
            solicitudes = RepositorioSolicitudes(repo)
            estado["tabla_lotes"] = bool(solicitudes.verificar_tabla())
            if estado["tabla_lotes"]:
                fila = solicitudes._ejecutar(
                    """SELECT max(finalizado_en) AS ultimo
                       FROM public.solicitudes_lote
                       WHERE worker_host = %s AND finalizado_en IS NOT NULL""",
                    (socket.gethostname()[:120],),
                    una=True,
                )
                if fila and fila["ultimo"]:
                    estado["ultimo_lote_finalizado"] = fila["ultimo"].isoformat()
    except Exception:
        # El tipo de error puede incluir la DSN; el estado basta para el operador.
        pass

    clave_captcha = os.environ.get("AUTOCAPTCHA_API_KEY")
    if estado["configuracion"] and clave_captcha:
        from src.servicio_captcha import Proveedor2Captcha

        try:
            Proveedor2Captcha(clave_captcha, config.get("captcha")).comprobar_disponibilidad()
            estado["captcha"] = True
        except Exception:
            pass

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    clave = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if url.startswith("https://") and clave:
        headers = {"apikey": clave}
        if clave.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + clave
        try:
            req = Request(url + "/storage/v1/bucket/lotes", headers=headers)
            with urlopen(req, timeout=12) as respuesta:
                estado["storage"] = respuesta.status == 200
        except (HTTPError, URLError, TimeoutError, ValueError):
            pass
    return estado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=RAIZ / "config_supabase.json")
    args = parser.parse_args()
    estado = comprobar(args.config)
    print(json.dumps(estado, ensure_ascii=False))
    return 0 if all(valor for clave, valor in estado.items() if clave != "ultimo_lote_finalizado") else 1


if __name__ == "__main__":
    raise SystemExit(main())
