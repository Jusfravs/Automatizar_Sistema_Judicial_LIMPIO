import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'

export type EmptyStateProps = {
  /** Icono decorativo (se marca aria-hidden). */
  icono?: ReactNode
  titulo: ReactNode
  descripcion?: ReactNode
  /** Siguiente paso: normalmente un ButtonLink o Button. */
  accion?: ReactNode
  className?: string
}

export function EmptyState({ icono, titulo, descripcion, accion, className }: EmptyStateProps) {
  return (
    <div
      className={cx(
        'flex flex-col items-center rounded-tarjeta border border-dashed border-subtle bg-surface px-6 py-10 text-center',
        className,
      )}
    >
      {icono ? (
        <div aria-hidden="true" className="mb-3 flex size-10 items-center justify-center rounded-full bg-surface-2 text-muted">
          {icono}
        </div>
      ) : null}
      <p className="text-base font-semibold text-fg text-balance">{titulo}</p>
      {descripcion ? <p className="mt-1 max-w-sm text-sm text-muted text-pretty">{descripcion}</p> : null}
      {accion ? <div className="mt-4">{accion}</div> : null}
    </div>
  )
}
