"""Interfaz de persistencia de ejecuciones y trabajos."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from src.ejecucion import TrabajoCola


@runtime_checkable
class RepositorioCola(Protocol):
    def verificar_conexion(self) -> bool: ...

    def verificar_esquema(self) -> bool: ...

    def crear_ejecucion(
        self, perfil: str, total_esperado: int, trabajadores: int
    ) -> str: ...

    def poblar_trabajos(self, ejecucion_id: str, causas: Iterable[str]) -> int: ...

    def iniciar_ejecucion(self, ejecucion_id: str) -> None: ...

    def reservar_siguiente(
        self, ejecucion_id: str, worker_id: str, lease_segundos: int
    ) -> TrabajoCola | None: ...

    def renovar_lease(
        self, trabajo_id: Any, worker_id: str, lease_segundos: int
    ) -> bool: ...

    def completar_trabajo(
        self,
        trabajo: TrabajoCola,
        worker_id: str,
        estado_final: str,
        resultado: Mapping[str, Any],
        origen: str,
        ciudad: str,
    ) -> None: ...

    def fallar_trabajo(
        self,
        trabajo: TrabajoCola,
        worker_id: str,
        detalle: str,
        resultado: Mapping[str, Any] | None,
        recuperable: bool,
        maximo_intentos: int,
    ) -> str: ...

    def recuperar_leases_vencidos(
        self, ejecucion_id: str, maximo_intentos: int
    ) -> int: ...

    def obtener_estadisticas(self, ejecucion_id: str) -> dict[str, int]: ...

    def listar_resultados(
        self, ejecucion_id: str, despues_de: int = 0
    ) -> list[dict[str, Any]]: ...

    def finalizar_ejecucion(self, ejecucion_id: str, estado: str) -> None: ...


def crear_repositorio_cola(config_db, ruta_sqlite=None):
    """Construye el adaptador solicitado sin realizar fallback silencioso."""
    config_db = dict(config_db or {})
    motor = str(config_db.get("motor", "sqlite")).lower()
    if motor == "sqlite":
        if not ruta_sqlite:
            raise ValueError("RUTA_SQLITE_REQUERIDA")
        from src.repositorio_sqlite import RepositorioColaSQLite

        return RepositorioColaSQLite(ruta_sqlite)
    if motor == "postgres":
        from src.repositorio_postgres import RepositorioColaPostgres

        return RepositorioColaPostgres.desde_config(config_db)
    raise ValueError("MOTOR_BASE_DATOS_NO_SOPORTADO:%s" % motor)
