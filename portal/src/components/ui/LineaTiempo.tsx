import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'

export type EstadoPaso = 'hecho' | 'actual' | 'pendiente' | 'fallo'

export type Paso = {
  clave: string
  etiqueta: string
  /** Texto secundario, normalmente la fecha ya formateada. */
  detalle?: ReactNode
  estado: EstadoPaso
}

export type LineaTiempoProps = {
  pasos: Paso[]
  /** Nombre accesible de la lista. Ej.: "Progreso del lote". */
  etiqueta: string
  className?: string
}

const PUNTO: Record<EstadoPaso, string> = {
  hecho: 'border-exito-solid bg-exito-solid',
  actual: 'border-progreso-solid bg-surface ring-4 ring-progreso-soft',
  pendiente: 'border-strong bg-surface',
  fallo: 'border-peligro-solid bg-peligro-solid',
}

// El estado también va en texto (sr-only): el color nunca es la única señal.
const TEXTO_ESTADO: Record<EstadoPaso, string> = {
  hecho: 'completado',
  actual: 'en curso',
  pendiente: 'pendiente',
  fallo: 'detenido',
}

/**
 * Línea de tiempo de pasos: vertical en móvil, horizontal desde sm.
 * El tramo entre dos pasos se pinta como alcanzado si el paso siguiente ya no está pendiente.
 */
export function LineaTiempo({ pasos, etiqueta, className }: LineaTiempoProps) {
  return (
    <ol aria-label={etiqueta} className={cx('flex flex-col gap-0 sm:flex-row', className)}>
      {pasos.map((paso, i) => {
        const siguiente = pasos[i + 1]
        const tramoAlcanzado = siguiente ? siguiente.estado !== 'pendiente' : false
        return (
          <li
            key={paso.clave}
            aria-current={paso.estado === 'actual' ? 'step' : undefined}
            className="relative flex min-w-0 flex-1 gap-3 pb-6 last:pb-0 sm:flex-col sm:gap-2 sm:pb-0 sm:pr-4 sm:last:pr-0"
          >
            {siguiente ? (
              <span
                aria-hidden="true"
                className={cx(
                  'absolute left-[7px] top-4 h-[calc(100%-1rem)] w-0.5 sm:left-4 sm:top-[7px] sm:h-0.5 sm:w-[calc(100%-1rem)]',
                  'transition-colors duration-(--duracion-movimiento)',
                  tramoAlcanzado ? 'bg-exito-solid' : 'bg-(--border-strong)',
                )}
              />
            ) : null}
            <span
              aria-hidden="true"
              className={cx(
                'relative z-10 mt-0.5 size-4 shrink-0 rounded-full border-2 transition-colors duration-(--duracion-movimiento) sm:mt-0',
                PUNTO[paso.estado],
              )}
            >
              {/* Paso en curso: onda suave de "vivo". */}
              {paso.estado === 'actual' ? <span className="absolute -inset-0.5 rounded-full bg-progreso-solid animate-latido" /> : null}
            </span>
            <div className="min-w-0 space-y-0.5">
              <p
                className={cx(
                  'text-sm',
                  paso.estado === 'pendiente' ? 'text-muted' : 'font-semibold text-fg',
                  paso.estado === 'fallo' && 'text-peligro-fg',
                )}
              >
                {paso.etiqueta}
                <span className="sr-only">, {TEXTO_ESTADO[paso.estado]}</span>
              </p>
              {paso.detalle ? <p className="text-xs tabular-nums text-muted">{paso.detalle}</p> : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
