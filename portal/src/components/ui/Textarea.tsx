import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import { CONTROL } from './estilos'

export function Textarea({ className, rows = 4, ...props }: ComponentProps<'textarea'>) {
  return <textarea rows={rows} className={cx(CONTROL, 'min-h-20 py-2 leading-5', className)} {...props} />
}
