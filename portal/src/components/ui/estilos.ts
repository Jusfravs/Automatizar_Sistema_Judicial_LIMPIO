import { cx } from '@/lib/cx'
import type { Tono } from '@/lib/tonos'

/*
 * Clases compartidas entre componentes de ui/. Solo tokens de globals.css.
 * Tailwind necesita ver cada clase completa en el código: por eso los mapas
 * por tono escriben la cadena entera en vez de armarla con `${tono}`.
 */

/** Anillo de foco visible del sistema (token --focus). */
export const FOCO = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus'

export type VarianteBoton = 'primario' | 'secundario' | 'fantasma' | 'peligro'
export type TamanoBoton = 'sm' | 'md'

const BOTON_BASE =
  'inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium transition active:scale-98'

const BOTON_VARIANTES: Record<VarianteBoton, string> = {
  primario: 'bg-primary text-on-primary hover:bg-primary-hover',
  secundario: 'border border-strong bg-surface text-fg hover:bg-surface-2',
  // Hereda el color del contexto: sirve igual sobre surface que sobre la barra azul.
  fantasma: 'text-current hover:bg-current/10',
  // peligro-fg como hover: más oscuro en claro, más claro en oscuro; contraste con on-solid >= 7:1 en ambos.
  peligro: 'bg-peligro-solid text-peligro-on-solid hover:bg-peligro-fg',
}

const BOTON_TAMANOS: Record<TamanoBoton, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-9 px-4 text-sm',
}

/** Deshabilitado sin bajar el contraste del texto (docs/system.md, sección 4). */
const BOTON_DESHABILITADO = 'cursor-not-allowed border border-subtle bg-surface-2 text-muted active:scale-100'

export function clasesBoton({
  variante = 'primario',
  tamano = 'md',
  deshabilitado = false,
  className,
}: {
  variante?: VarianteBoton
  tamano?: TamanoBoton
  deshabilitado?: boolean
  className?: string
}): string {
  return cx(BOTON_BASE, FOCO, BOTON_TAMANOS[tamano], deshabilitado ? BOTON_DESHABILITADO : BOTON_VARIANTES[variante], className)
}

/** Input, Select y Textarea: token de control (borde fuerte >= 3:1, hover a tinta, foco visible). */
export const CONTROL = cx(
  'block w-full rounded-control border border-strong bg-surface px-3 text-sm text-fg transition-colors',
  'placeholder:text-muted hover:border-fg',
  FOCO,
  'disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted disabled:hover:border-strong',
  'aria-invalid:border-peligro-solid',
)

/** Chip de estado: fondo soft + texto fg. */
export const TONO_SUAVE: Record<Tono, string> = {
  neutral: 'bg-neutral-soft text-neutral-fg',
  info: 'bg-info-soft text-info-fg',
  progreso: 'bg-progreso-soft text-progreso-fg',
  exito: 'bg-exito-soft text-exito-fg',
  peligro: 'bg-peligro-soft text-peligro-fg',
  atencion: 'bg-atencion-soft text-atencion-fg',
}

/** Borde del tono (decorativo); para chips sobre surface-2 y avisos. */
export const TONO_BORDE: Record<Tono, string> = {
  neutral: 'border border-neutral-border',
  info: 'border border-info-border',
  progreso: 'border border-progreso-border',
  exito: 'border border-exito-border',
  peligro: 'border border-peligro-border',
  atencion: 'border border-atencion-border',
}

/** Relleno fuerte: punto indicador, barra de progreso. */
export const TONO_SOLIDO: Record<Tono, string> = {
  neutral: 'bg-neutral-solid',
  info: 'bg-info-solid',
  progreso: 'bg-progreso-solid',
  exito: 'bg-exito-solid',
  peligro: 'bg-peligro-solid',
  atencion: 'bg-atencion-solid',
}
