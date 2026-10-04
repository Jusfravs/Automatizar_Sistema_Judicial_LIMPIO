"""Interfaz de consola para preparar, ejecutar y revisar lotes judiciales."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from src.configuracion_lotes import (
    actualizar_casos,
    cargar_comun,
    configuracion_efectiva,
    guardar_json_atomico,
    leer_manifiesto,
    migrar_lote_anterior,
)
from src.normalizacion_excel import leer_y_validar


RAIZ = Path(__file__).resolve().parent
CONFIG_COMUN = RAIZ / "config_consola.json"


def _json(valor):
    print(json.dumps(valor, ensure_ascii=False, indent=2, default=str))


def _retirar_temporal(temporal: Path, padre: Path) -> None:
    ruta = temporal.resolve()
    if ruta.parent != padre.resolve() or not ruta.name.startswith(".preparar_"):
        raise ValueError("RUTA_TEMPORAL_INVALIDA")
    shutil.rmtree(ruta)


def preparar(excel: Path, salida: Path, base: Path = CONFIG_COMUN, hoja: str | None = None) -> dict:
    """Prepara un lote o reabre el mismo Excel por su huella."""
    excel = excel.expanduser().resolve()
    salida = salida.expanduser().resolve()
    base = base.expanduser().resolve()
    cargar_comun(base)
    datos, resumen = leer_y_validar(excel, hoja)
    if salida.parent.is_dir():
        for candidato in salida.parent.iterdir():
            if (candidato.is_dir() and not candidato.name.startswith(".preparar_")
                    and (candidato / "manifiesto.json").is_file()):
                existente = leer_manifiesto(candidato)
                if existente["sha256"] == resumen["sha256"]:
                    migrar_lote_anterior(candidato, base)
                    actualizar_casos(candidato, base)
                    return {"directorio": str(candidato), "config": str(base),
                            "reutilizado": True, **resumen}
    if salida.exists():
        raise ValueError(f"DESTINO_YA_EXISTE:{salida}")
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = Path(tempfile.mkdtemp(prefix=".preparar_", dir=salida.parent))
    try:
        origen = temporal / "origen.xlsx"
        shutil.copy2(excel, origen)
        # La copia se verifica para no operar sobre un Excel cambiado durante la lectura.
        _, resumen_copia = leer_y_validar(origen, resumen["hoja"])
        if resumen_copia["sha256"] != resumen["sha256"]:
            raise ValueError("EXCEL_CAMBIO_DURANTE_PREPARACION")
        datos.to_csv(temporal / "reporte_trabajo.csv", index=False, encoding="utf-8-sig")
        shutil.copy2(temporal / "reporte_trabajo.csv", temporal / "reporte_trabajo.csv.bak")
        (temporal / "casos_fallidos.txt").touch()
        guardar_json_atomico(temporal / "manifiesto.json", {
            "version": 2, "perfil_id": f"lote-{resumen['sha256']}",
            "excel_original": str(excel), **resumen,
        })
        actualizar_casos(temporal, base)
        try:
            temporal.rename(salida)
        except OSError:
            if (salida / "manifiesto.json").is_file() and leer_manifiesto(salida)["sha256"] == resumen["sha256"]:
                _retirar_temporal(temporal, salida.parent)
                actualizar_casos(salida, base)
                return {"directorio": str(salida), "config": str(base),
                        "reutilizado": True, **resumen}
            raise
    except Exception:
        _retirar_temporal(temporal, salida.parent)
        raise
    return {"directorio": str(salida), "config": str(base), "reutilizado": False, **resumen}


def _config_perfil(perfil: Path, base: Path = CONFIG_COMUN) -> dict:
    migrar_lote_anterior(perfil, base)
    return configuracion_efectiva(perfil, base)


def _repositorio(config: dict):
    from src.repositorio_postgres import RepositorioColaPostgres

    repo = RepositorioColaPostgres.desde_config(config["base_de_datos"])
    if not repo.password:
        raise ValueError("POSTGRES_PASSWORD_NO_CONFIGURADA")
    if repo.host not in {"localhost", "127.0.0.1", "::1"} and repo.sslmode != "verify-full":
        raise ValueError("POSTGRES_REMOTO_REQUIERE_SSLMODE_VERIFY_FULL")
    return repo


def diagnostico(config: dict) -> dict:
    repo = _repositorio(config)
    return {
        "servidor": repo.host,
        "base": repo.dbname,
        "tls": repo.sslmode or "predeterminado_de_libpq",
        "conexion": repo.verificar_conexion(),
        "esquema_completo": repo.verificar_esquema(),
        "auditoria_config": repo.verificar_auditoria_config(),
    }


def aplicar_migraciones(config: dict, usuario_admin: str, password_admin: str) -> None:
    """Aplica solo la migración 003 con credencial administrativa temporal."""
    if not usuario_admin or not password_admin:
        raise ValueError("CREDENCIAL_ADMIN_REQUERIDA")
    repo = _repositorio(config)
    import psycopg2

    migracion = RAIZ / "migrations" / "postgres" / "003_config_comun_auditoria.sql"
    contenido = migracion.read_text(encoding="utf-8")
    huella = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    tls = {}
    if repo.sslmode:
        tls["sslmode"] = repo.sslmode
    if repo.sslrootcert:
        tls["sslrootcert"] = repo.sslrootcert
    conn = psycopg2.connect(host=repo.host, port=repo.port, dbname=repo.dbname,
                            user=usuario_admin, password=password_admin,
                            connect_timeout=10, **tls)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL search_path TO public")
                cur.execute("SELECT checksum FROM public.schema_migrations WHERE version = %s",
                            (migracion.name,))
                anterior = cur.fetchone()
                if anterior:
                    if anterior[0].strip() != huella:
                        raise ValueError("MIGRACION_003_CHECKSUM_DISTINTO")
                    return
                cur.execute(contenido)
                cur.execute("INSERT INTO public.schema_migrations (version, checksum) VALUES (%s, %s)",
                            (migracion.name, huella))
    finally:
        conn.close()


def ejecuciones(config: dict, limite: int = 10, solo_errores: bool = False) -> list[dict]:
    repo = _repositorio(config)
    with repo._connection() as conn:
        from psycopg2.extras import RealDictCursor

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if solo_errores:
                cur.execute(
                    """SELECT c.ejecucion_id, c.numero_causa, c.estado, c.intentos,
                              c.ultimo_error, c.actualizado_en
                       FROM cola_trabajo c
                       JOIN ejecuciones e ON e.id = c.ejecucion_id
                       WHERE c.estado IN ('ERROR_FINAL', 'ERROR_REINTENTABLE',
                                          'REVISION', 'SIN_RESULTADOS', 'PARCIAL')
                         AND e.perfil = %s
                       ORDER BY c.actualizado_en DESC LIMIT %s""",
                    (config["perfil"], limite),
                )
            else:
                cur.execute(
                    "SELECT * FROM v_estado_ejecuciones WHERE perfil = %s ORDER BY creado_en DESC LIMIT %s",
                    (config["perfil"], limite),
                )
            return [dict(fila) for fila in cur.fetchall()]


def ejecutar_lote(perfil: Path, *, solo: str | None = None, lote: int | None = None,
                  workers: int = 2, continuar: bool = False, base: Path = CONFIG_COMUN,
                  config: dict | None = None):
    """Procesa un lote preparado con el bloqueo exclusivo de su perfil."""
    if config is None:
        config = _config_perfil(perfil, base)
    revision = diagnostico(config)
    if not revision["esquema_completo"]:
        raise ValueError("ESQUEMA_POSTGRES_INCOMPLETO")
    if not revision["auditoria_config"]:
        raise ValueError("MIGRACION_003_PENDIENTE")
    if continuar and solo:
        raise ValueError("CONTINUAR_NO_ADMITIDO_CON_SOLO")
    actualizar_casos(perfil, base)
    opciones = ["--config", str(base)]
    if solo:
        opciones += ["--solo", solo]
    elif lote is not None:
        opciones += ["--lote", str(lote)]
    else:
        opciones += ["--pendientes"]
    if continuar:
        opciones.append("--omitir-procesados")
    opciones += ["--workers", str(workers)]
    import main as motor

    repo = _repositorio(config)
    llave = int.from_bytes(hashlib.sha256(config["perfil"].encode()).digest()[:8], "big") & ((1 << 63) - 1)
    with repo._connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (llave,))
            if not cur.fetchone()[0]:
                raise ValueError("PERFIL_YA_EN_EJECUCION")
        try:
            return motor.main(opciones, config_efectiva=config)
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (llave,))


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("menu", help="Abrir menú interactivo en la terminal")
    validar = sub.add_parser("validar", help="Inspeccionar un Excel sin escribir archivos")
    validar.add_argument("excel", type=Path)
    validar.add_argument("--hoja")
    nuevo = sub.add_parser("preparar", help="Normalizar Excel y crear perfil aislado")
    nuevo.add_argument("excel", type=Path)
    nuevo.add_argument("--salida", required=True, type=Path)
    nuevo.add_argument("--hoja")
    ejecutar = sub.add_parser("ejecutar", help="Procesar causas con el motor actual")
    ejecutar.add_argument("perfil", type=Path)
    modos = ejecutar.add_mutually_exclusive_group(required=True)
    modos.add_argument("--solo")
    modos.add_argument("--lote", type=int)
    modos.add_argument("--pendientes", action="store_true")
    ejecutar.add_argument("--workers", type=int, default=2)
    ejecutar.add_argument("--continuar", action="store_true",
                          help="Omitir causas ya procesadas en esta base")
    servicio = sub.add_parser("servicio", help="Atender los lotes solicitados desde el portal web")
    servicio.add_argument("--config", type=Path, default=RAIZ / "config_supabase.json")
    servicio.add_argument("--intervalo", type=int, default=10,
                          help="Segundos entre consultas cuando no hay solicitudes")
    servicio.add_argument("--una-vez", action="store_true",
                          help="Atender a lo sumo una solicitud y salir")
    for nombre in ("diagnostico", "estado", "errores"):
        comando = sub.add_parser(nombre)
        comando.add_argument("perfil", type=Path)
        if nombre in ("estado", "errores"):
            comando.add_argument("--limite", type=int, default=10)
    return parser


def menu() -> int:
    from src.interfaz_cmd import InterfazCMD

    return InterfazCMD(sys.modules[__name__]).iniciar()


def main(argv=None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    args = construir_parser().parse_args(argumentos or ["menu"])
    try:
        if args.comando == "menu":
            return menu()
        if args.comando == "validar":
            _, resumen = leer_y_validar(args.excel, args.hoja)
            _json(resumen)
        elif args.comando == "preparar":
            _json(preparar(args.excel, args.salida, CONFIG_COMUN, args.hoja))
        elif args.comando == "servicio":
            if args.intervalo < 2 or args.intervalo > 300:
                raise ValueError("INTERVALO_FUERA_DE_RANGO:2..300")
            from src.servicio_portal import ejecutar_servicio

            return ejecutar_servicio(args.config, intervalo=args.intervalo, una_vez=args.una_vez)
        else:
            config = _config_perfil(args.perfil)
            if args.comando == "diagnostico":
                _json(diagnostico(config))
            elif args.comando in ("estado", "errores"):
                if args.limite < 1 or args.limite > 500:
                    raise ValueError("LIMITE_FUERA_DE_RANGO:1..500")
                _json(ejecuciones(config, args.limite, args.comando == "errores"))
            elif args.comando == "ejecutar":
                resultado = ejecutar_lote(
                    args.perfil, solo=args.solo, lote=args.lote, workers=args.workers,
                    continuar=args.continuar, config=config,
                )
                if resultado is not None:
                    _json(resultado)
                    if resultado.get("estado") != "COMPLETADA":
                        return 1
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
