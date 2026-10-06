import type { ComponentProps, ReactNode } from 'react'
import { cx } from '@/lib/cx'

/** Superficie elevada sobre bg: tarjetas, formularios, bloques de detalle. */
export function Card({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cx('rounded-tarjeta bg-surface text-fg shadow-tarjeta', className)} {...props} />
}

export type CardHeaderProps = Omit<ComponentProps<'div'>, 'title'> & {
  titulo: ReactNode
  descripcion?: ReactNode
  acciones?: ReactNode
  /** Nivel del encabezado. 2 si la tarjeta cuelga del h1 de la página; 3 si va dentro de una sección. */
  nivel?: 2 | 3
}

export function CardHeader({ titulo, descripcion, acciones, nivel = 2, className, ...props }: CardHeaderProps) {
  const Encabezado = nivel === 2 ? 'h2' : 'h3'
  return (
    <div
      className={cx('flex flex-wrap items-start justify-between gap-3 border-b border-subtle px-4 py-3 sm:px-6', className)}
      {...props}
    >
      <div className="min-w-0">
        <Encabezado className="text-base font-semibold text-fg text-balance">{titulo}</Encabezado>
        {descripcion ? <p className="mt-0.5 text-sm text-muted text-pretty">{descripcion}</p> : null}
      </div>
      {acciones ? <div className="flex shrink-0 flex-wrap items-center gap-2">{acciones}</div> : null}
    </div>
  )
}

export function CardBody({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cx('p-4 sm:p-6', className)} {...props} />
}
