import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import { CONTROL } from './estilos'

/** Select nativo con el token de control (teclado y lectores de pantalla nativos). */
export function Select({ className, ...props }: ComponentProps<'select'>) {
  return <select className={cx(CONTROL, 'h-9 cursor-pointer pr-8', className)} {...props} />
}
