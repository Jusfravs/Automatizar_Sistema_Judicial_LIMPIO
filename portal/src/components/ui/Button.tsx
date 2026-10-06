import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import { Spinner } from './iconos'
import { clasesBoton, type TamanoBoton, type VarianteBoton } from './estilos'

export type ButtonProps = ComponentProps<'button'> & {
  variante?: VarianteBoton
  tamano?: TamanoBoton
  /** Muestra un spinner, deshabilita el botón y anuncia aria-busy. Conserva el aspecto de la variante. */
  cargando?: boolean
}

export function Button({
  variante = 'primario',
  tamano = 'md',
  cargando = false,
  disabled,
  type = 'button',
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || cargando}
      aria-busy={cargando || undefined}
      className={clasesBoton({
        variante,
        tamano,
        deshabilitado: Boolean(disabled) && !cargando,
        className: cx(cargando && 'cursor-wait', className),
      })}
      {...props}
    >
      {cargando ? <Spinner /> : null}
      {children}
    </button>
  )
}
