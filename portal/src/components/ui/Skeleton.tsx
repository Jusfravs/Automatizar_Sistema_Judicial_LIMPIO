import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'

/** Bloque de carga. Dale tamaño con className (h-4 w-32…). Es decorativo: anuncia la carga en el contenedor (aria-busy). */
export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return <div aria-hidden="true" className={cx('animate-pulse rounded-control bg-surface-2', className)} {...props} />
}
