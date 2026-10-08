import type { ComponentProps, MouseEvent } from 'react'
import { cx } from '@/lib/cx'
import { Spinner } from './iconos'
import { clasesBoton, type TamanoBoton, type VarianteBoton } from './estilos'

export type ButtonProps = ComponentProps<'button'> & {
  variante?: VarianteBoton
  tamano?: TamanoBoton
  /**
   * Muestra un spinner, bloquea el botón y anuncia aria-busy. Conserva el aspecto de la variante
   * y el ancho: la etiqueta se vuelve transparente (sigue siendo el nombre accesible) y el spinner
   * ocupa su lugar, así el botón no salta. Usa aria-disabled en vez de disabled para que el foco
   * no salga expulsado al <body> mientras carga.
   */
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
  onClick,
  ...props
}: ButtonProps) {
  function alPulsar(e: MouseEvent<HTMLButtonElement>) {
    // Bloquea también el envío implícito (Enter en un campo dispara un clic en el botón de envío).
    if (cargando) {
      e.preventDefault()
      return
    }
    onClick?.(e)
  }

  return (
    <button
      type={type}
      disabled={disabled && !cargando}
      aria-disabled={cargando || undefined}
      aria-busy={cargando || undefined}
      onClick={alPulsar}
      className={clasesBoton({
        variante,
        tamano,
        deshabilitado: Boolean(disabled) && !cargando,
        className: cx(cargando && 'cursor-wait', className),
      })}
      {...props}
    >
      {/* Etiqueta y spinner comparten la misma celda de grid: sin posicionar el botón (puede ser absolute). */}
      <span className="inline-grid place-items-center">
        <span
          className={cx(
            'col-start-1 row-start-1 inline-flex items-center gap-2 transition-opacity duration-(--duracion-rapida)',
            cargando && 'opacity-0',
          )}
        >
          {children}
        </span>
        {cargando ? (
          <span className="col-start-1 row-start-1 inline-flex">
            <Spinner />
          </span>
        ) : null}
      </span>
    </button>
  )
}
