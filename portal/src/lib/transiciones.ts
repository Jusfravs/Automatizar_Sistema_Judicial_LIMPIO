/**
 * Tipos de View Transition. Solo la navegación explícita lleva "navegacion" y funde el contenido
 * (AppShell). Refrescos, filtros, orden y paginación no llevan tipo: son silenciosos.
 * Úsalo en <Link transitionTypes={NAVEGACION}> y router.push(url, { transitionTypes: NAVEGACION }).
 */
export const NAVEGACION = ['navegacion']
