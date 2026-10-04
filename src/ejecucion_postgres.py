"""Despacho de lotes judiciales mediante la cola PostgreSQL."""

from src.seleccion_ejecucion import _causa_comparable, seleccionar_casos


def ejecutar_lote_postgres(
    repo,
    argumentos,
    ruta_config,
    ruta_casos_fallidos,
    trabajadores,
    *,
    guardar_casos_fallidos,
    logger,
):
    """Selecciona causas y ejecuta el lote PostgreSQL con sus trabajadores."""
    modo_limitado = argumentos[:1] in (
        ["--solo"],
        ["--lote"],
        ["--pendientes"],
        ["--reprocesar-filtro"],
    )
    if modo_limitado:
        repo.filtros["inicio_desde_juicio"] = None
    candidatos = repo.obtener_casos_pendientes()
    if argumentos[:1] in (["--lote"], ["--pendientes"]) and "--omitir-procesados" in argumentos:
        if argumentos.count("--omitir-procesados") != 1:
            raise ValueError("OPCION_OMITIR_PROCESADOS_DUPLICADA")
        from src.repositorio_postgres import RepositorioColaPostgres

        repositorio_pg = RepositorioColaPostgres.desde_config(
            repo.config["base_de_datos"]
        )
        perfil = repo.config.get("perfil")
        causas_procesadas = (
            repositorio_pg.listar_causas_procesadas(perfil=perfil)
            if perfil else repositorio_pg.listar_causas_procesadas()
        )
        procesadas = {
            _causa_comparable(causa)
            for causa in causas_procesadas
        }
        pendientes = []
        vistos = set(procesadas)
        for causa in candidatos:
            comparable = _causa_comparable(causa)
            if comparable and comparable not in vistos:
                vistos.add(comparable)
                pendientes.append(causa)
        candidatos = pendientes
        logger.info(
            "[POSTGRES] Continuacion: %s causas unicas disponibles tras omitir procesadas.",
            len(candidatos),
        )
        argumentos = [
            argumento for argumento in argumentos
            if argumento != "--omitir-procesados"
        ]
    casos = seleccionar_casos(candidatos, argumentos)
    if not casos:
        logger.info("[-] No existen juicios pendientes para procesar.")
        guardar_casos_fallidos([], ruta_casos_fallidos)
        return None

    from src.coordinador_concurrente import CoordinadorConcurrente

    logger.info(
        "[POSTGRES] Preparando %s causas con %s trabajador(es).",
        len(casos),
        trabajadores,
    )
    coordinador = CoordinadorConcurrente(
        repo,
        ruta_config,
        trabajadores=trabajadores,
    )
    resultado = coordinador.ejecutar(casos, ruta_casos_fallidos)
    logger.info(
        "[POSTGRES] Ejecucion %s finalizada como %s: %s",
        resultado["ejecucion_id"],
        resultado["estado"],
        resultado["estadisticas"],
    )
    return resultado
