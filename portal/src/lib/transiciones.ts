/**
 * Tipos de View Transition. Solo la navegación explícita lleva tipo y anima el contenido
 * (AppShell). Refrescos, filtros, orden y paginación no llevan tipo: son silenciosos.
 * Úsalos en <Link transitionTypes={…}> y router.push(url, { transitionTypes: … }).
 *
 * - NAVEGACION: entre secciones (barra lateral, accesos de Inicio). Fundido.
 * - ADELANTE: bajar un nivel (fila de una lista → su detalle). La vista nueva entra desde la derecha.
 * - ATRAS: subir un nivel (migas de pan, "Volver a…"). La vista nueva entra desde la izquierda.
 */
export const NAVEGACION = ['navegacion']
export const ADELANTE = ['adelante']
export const ATRAS = ['atras']
