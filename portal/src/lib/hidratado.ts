import { useSyncExternalStore } from 'react'

const sinSuscripcion = () => () => {}

/**
 * false durante el render del servidor y la hidratación; true después. Sirve para animar solo lo
 * que aparece tras cargar la vista (p. ej. .despliegue) sin desajustes de hidratación.
 */
export function useHidratado(): boolean {
  return useSyncExternalStore(
    sinSuscripcion,
    () => true,
    () => false,
  )
}
