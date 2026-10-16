"""Compara expedientes guardados, sin modificar su estado oficial.

Ejemplo: python -m scripts.inferencia_dual_sombra --config config.json --limite 20 --sin-guardar
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.agente_extractor import MotorInferenciaProcesal
from src.inferencia_dual import comparar, guardar_postgres, huella_motor
from src.proveedor_nvidia import MODELO_PREDETERMINADO, VERSION_PROMPT_INFERENCIA
from src.repositorio_postgres import RepositorioColaPostgres


def ejecutar(ruta_config: Path, limite: int, causas: list[str] | None = None,
            *, sin_guardar: bool = False, sin_red: bool = False) -> dict:
    config = json.loads(ruta_config.read_text(encoding="utf-8-sig"))
    if config.get("base_de_datos", {}).get("motor") != "postgres":
        raise ValueError("INFERENCIA_DUAL_REQUIERE_POSTGRES")
    ia = config.get("inferencia_ia") or {}
    modelo = ia.get("modelo") or MODELO_PREDETERMINADO
    repo = RepositorioColaPostgres.desde_config(config["base_de_datos"])
    resumen = {"vistos": 0, "comparados": 0, "coinciden_actual": 0,
               "coinciden_ultimo": 0, "insuficientes": 0, "errores": 0,
               "omitidos": 0, "sin_payload": 0, "sin_actuaciones": 0, "sin_motor": 0,
               "preparados": 0, "guardados": 0, "tokens": 0,
               "latencia_ms_total": 0, "circuito_abierto": False}
    conn = repo._get_connection()
    try:
        if sin_guardar:
            conn.set_session(readonly=True)
        elif not sin_red:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.inferencias_ia')")
                if cur.fetchone()[0] is None:
                    raise RuntimeError("MIGRACION_011_PENDIENTE")
        with conn.cursor() as cur:
            if causas:
                cur.execute("""
                    SELECT numero_causa, datos_json FROM expedientes
                    WHERE numero_causa = ANY(%s) AND datos_json IS NOT NULL
                    AND EXISTS (SELECT 1 FROM actuaciones_procesales a
                                WHERE a.numero_causa=expedientes.numero_causa
                                AND a.titulo <> '')
                    ORDER BY numero_causa LIMIT %s
                """, (causas, limite))
            else:
                cur.execute("""
                    SELECT numero_causa, datos_json FROM expedientes
                    WHERE datos_json IS NOT NULL
                    AND EXISTS (SELECT 1 FROM actuaciones_procesales a
                                  WHERE a.numero_causa=expedientes.numero_causa
                                  AND a.titulo <> '')
                    ORDER BY numero_causa LIMIT %s
                """, (limite,))
            filas = cur.fetchall()
        for numero_causa, payload in filas:
            resumen["vistos"] += 1
            if not isinstance(payload, dict):
                resumen["omitidos"] += 1
                resumen["sin_payload"] += 1
                continue
            datos = payload.get("datos") if isinstance(payload.get("datos"), dict) else payload
            datos = dict(datos)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT actuacion_id, fecha, titulo, detalle, carpeta FROM actuaciones_procesales
                    WHERE numero_causa=%s AND titulo <> '' ORDER BY fecha, actuacion_id
                """, (numero_causa,))
                actuaciones = [
                    {"actuacion_id": act_id, "fecha": f, "titulo": t,
                     "detalle": d, "carpeta": c}
                    for act_id, f, t, d, c in cur.fetchall()
                ]
            if not actuaciones:
                resumen["omitidos"] += 1
                resumen["sin_actuaciones"] += 1
                continue
            try:
                motor = MotorInferenciaProcesal.inferir_estado_procesal(
                    actuaciones, causa=numero_causa
                )
                if not motor or not motor.get("ULTIMA_ETAPA"):
                    resumen["omitidos"] += 1
                    resumen["sin_motor"] += 1
                    continue
                huella = huella_motor(numero_causa, datos, actuaciones, motor)
                resumen["preparados"] += 1
                if not sin_guardar and not sin_red:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT error FROM inferencias_ia
                            WHERE numero_causa=%s AND huella_contexto=%s
                            AND modelo=%s AND version_prompt=%s
                        """, (numero_causa, huella, modelo, VERSION_PROMPT_INFERENCIA))
                        previa = cur.fetchone()
                    if previa and previa[0] in (None, "INSUFICIENTE"):
                        resumen["omitidos"] += 1
                        continue
                if sin_red:
                    continue
                registro, _ = comparar(numero_causa, datos, actuaciones, motor, ia)
                if registro["error"]:
                    if registro["error"] == "INSUFICIENTE":
                        resumen["insuficientes"] += 1
                    else:
                        resumen["errores"] += 1
                else:
                    resumen["comparados"] += 1
                    resumen["coinciden_actual"] += int(registro["coincide_actual"] is True)
                    resumen["coinciden_ultimo"] += int(registro["coincide_ultimo"] is True)
                resumen["tokens"] += registro["tokens"] or 0
                resumen["latencia_ms_total"] += registro["latencia_ms"] or 0
                if not sin_guardar:
                    guardar_postgres(conn, registro)
                    conn.commit()
                    resumen["guardados"] += 1
                if registro["error"] in {
                    "HTTP_401", "HTTP_402", "CIRCUITO_ABIERTO", "NVIDIA_API_KEY_AUSENTE"
                }:
                    resumen["circuito_abierto"] = True
                    break
            except (ValueError, TypeError, KeyError):
                conn.rollback()
                resumen["errores"] += 1
        return resumen
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--causas", nargs="*")
    parser.add_argument("--sin-guardar", action="store_true",
                        help="Transacción PostgreSQL de solo lectura; llamadas NVIDIA activas")
    parser.add_argument("--sin-red", action="store_true",
                        help="Solo selecciona y ejecuta el motor; no llama a NVIDIA")
    args = parser.parse_args()
    if not 1 <= args.limite <= 100:
        parser.error("--limite debe estar entre 1 y 100")
    if args.sin_red and not args.sin_guardar:
        parser.error("--sin-red requiere --sin-guardar")
    print(json.dumps(ejecutar(
        args.config, args.limite, args.causas,
        sin_guardar=args.sin_guardar, sin_red=args.sin_red,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
