import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'

/** Props de accesibilidad que Field entrega al control. Espárcelas en el input: `<Input {...a11y} />`. */
export type CampoA11y = {
  id: string
  'aria-describedby': string | undefined
  'aria-invalid': true | undefined
}

/** Ids derivados de `htmlFor`. Úsalos si prefieres cablear el control a mano en vez del render-prop. */
export function idsCampo(htmlFor: string): { ayudaId: string; errorId: string } {
  return { ayudaId: `${htmlFor}-ayuda`, errorId: `${htmlFor}-error` }
}

/** Calcula las props aria-* de un control según tenga ayuda o error. */
export function a11yCampo(htmlFor: string, { ayuda, error }: { ayuda?: ReactNode; error?: ReactNode }): CampoA11y {
  const { ayudaId, errorId } = idsCampo(htmlFor)
  const describedBy = [error ? errorId : null, ayuda ? ayudaId : null].filter(Boolean).join(' ')
  return {
    id: htmlFor,
    'aria-describedby': describedBy || undefined,
    'aria-invalid': error ? true : undefined,
  }
}

export type FieldProps = {
  label: ReactNode
  /** id del control; también es la base de los ids de ayuda y error. */
  htmlFor: string
  ayuda?: ReactNode
  error?: ReactNode
  /**
   * El control. Como función recibe `{ id, aria-describedby, aria-invalid }` listos para esparcir.
   * Como nodo, el control debe llevar esas props a mano (ver `a11yCampo`).
   */
  children: ReactNode | ((a11y: CampoA11y) => ReactNode)
  className?: string
}

export function Field({ label, htmlFor, ayuda, error, children, className }: FieldProps) {
  const { ayudaId, errorId } = idsCampo(htmlFor)
  const control = typeof children === 'function' ? children(a11yCampo(htmlFor, { ayuda, error })) : children
  return (
    <div className={cx('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-muted">
        {label}
      </label>
      {control}
      {ayuda ? (
        <p id={ayudaId} className="text-xs text-muted text-pretty">
          {ayuda}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-peligro-fg text-pretty">
          {error}
        </p>
      ) : null}
    </div>
  )
}
