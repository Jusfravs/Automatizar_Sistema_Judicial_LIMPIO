import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import type { Tono } from '@/lib/tonos'
import { TONO_BORDE, TONO_SOLIDO, TONO_SUAVE } from './estilos'

export type BadgeProps = ComponentProps<'span'> & {
  tono?: Tono
  /** Punto de relleno fuerte delante del texto. Refuerza, no sustituye, a la palabra. */
  punto?: boolean
  /** Contorno del tono; úsalo cuando el chip va sobre surface-2. */
  borde?: boolean
}

export function Badge({ tono = 'neutral', punto = false, borde = false, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cx(
        'inline-flex max-w-full items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium',
        TONO_SUAVE[tono],
        borde && TONO_BORDE[tono],
        className,
      )}
      {...props}
    >
      {punto ? <span aria-hidden="true" className={cx('size-1.5 shrink-0 rounded-full', TONO_SOLIDO[tono])} /> : null}
      <span className="truncate">{children}</span>
    </span>
  )
}
