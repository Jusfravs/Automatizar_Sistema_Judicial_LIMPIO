import { ViewTransition, type ReactNode } from 'react'

/** Nombre de View Transition válido (custom-ident) y único por causa. */
export function nombreTransicionCausa(numero: string): string {
  return `causa-${numero.replace(/[^a-zA-Z0-9_-]/g, '_')}`
}

/**
 * Número de causa como elemento compartido entre la lista y el detalle: al abrir una causa, el
 * número "viaja" de la fila al título (globals.css, clase "texto-compartido"). Debe haber una sola
 * instancia montada por causa; en DataTable úsalo solo en la vista de tabla.
 */
export function NumeroCausaCompartido({ numero, children }: { numero: string; children: ReactNode }) {
  return (
    <ViewTransition name={nombreTransicionCausa(numero)} share="texto-compartido" default="none">
      <span className="inline-block">{children}</span>
    </ViewTransition>
  )
}
