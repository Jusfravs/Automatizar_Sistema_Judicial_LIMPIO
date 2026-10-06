import type { ComponentProps, ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from './estilos'

export type CheckboxProps = Omit<ComponentProps<'input'>, 'type'> & {
  /** Texto de la casilla. Si se omite, el control necesita su propia etiqueta (aria-label o <label htmlFor>). */
  label?: ReactNode
}

export const CLASE_MARCA = cx('size-4 shrink-0 cursor-pointer accent-primary disabled:cursor-not-allowed', FOCO)

export const CLASE_ETIQUETA_MARCA =
  'inline-flex min-h-9 cursor-pointer items-center gap-2 text-sm text-fg has-[:disabled]:cursor-not-allowed has-[:disabled]:text-muted'

export function Checkbox({ label, className, ...props }: CheckboxProps) {
  const control = <input type="checkbox" className={cx(CLASE_MARCA, label ? undefined : className)} {...props} />
  if (!label) return control
  return (
    <label className={cx(CLASE_ETIQUETA_MARCA, className)}>
      {control}
      <span>{label}</span>
    </label>
  )
}
