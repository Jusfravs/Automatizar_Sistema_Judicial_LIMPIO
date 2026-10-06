import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import { CONTROL } from './estilos'

/** Campo de texto con el token de control. Combínalo con Field para la etiqueta y los aria-*. */
export function Input({ type = 'text', className, ...props }: ComponentProps<'input'>) {
  return <input type={type} className={cx(CONTROL, 'h-9', className)} {...props} />
}
