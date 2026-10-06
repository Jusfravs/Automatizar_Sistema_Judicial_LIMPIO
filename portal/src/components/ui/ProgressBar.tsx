import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import type { Tono } from '@/lib/tonos'
import { TONO_SOLIDO } from './estilos'

export type ProgressBarProps = Omit<ComponentProps<'div'>, 'role' | 'children'> & {
  /** Avance de 0 a 100; se recorta a ese rango. */
  valor: number
  /** Nombre accesible (aria-label). Ej.: "Avance del lote". */
  etiqueta: string
  tono?: Tono
}

export function ProgressBar({ valor, etiqueta, tono = 'progreso', className, ...props }: ProgressBarProps) {
  const v = Number.isFinite(valor) ? Math.min(100, Math.max(0, Math.round(valor))) : 0
  return (
    <div
      role="progressbar"
      aria-label={etiqueta}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={v}
      aria-valuetext={`${v} %`}
      className={cx('h-2 w-full overflow-hidden rounded-full bg-surface-2', className)}
      {...props}
    >
      {/* Se anima el ancho (así lo pide la especificación); reduced-motion lo anula vía globals.css. */}
      <div
        className={cx('h-full rounded-full transition-[width] duration-(--duracion-lenta) ease-salida', TONO_SOLIDO[tono])}
        style={{ width: `${v}%` }}
      />
    </div>
  )
}
