import type { ComponentProps, ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { CLASE_ETIQUETA_MARCA, CLASE_MARCA } from './Checkbox'

export type RadioProps = Omit<ComponentProps<'input'>, 'type'> & {
  label?: ReactNode
}

/** Opción de un grupo. Agrupa varias en <fieldset><legend>…</legend></fieldset> con el mismo `name`. */
export function Radio({ label, className, ...props }: RadioProps) {
  const control = <input type="radio" className={cx(CLASE_MARCA, label ? undefined : className)} {...props} />
  if (!label) return control
  return (
    <label className={cx(CLASE_ETIQUETA_MARCA, className)}>
      {control}
      <span>{label}</span>
    </label>
  )
}
