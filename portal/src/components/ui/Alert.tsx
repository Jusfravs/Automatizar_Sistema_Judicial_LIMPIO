import type { ComponentProps, ReactNode } from 'react'
import { cx } from '@/lib/cx'
import type { Tono } from '@/lib/tonos'
import { IconoAtencion, IconoExito, IconoInfo, IconoPeligro } from './iconos'

export type TonoAlerta = Extract<Tono, 'info' | 'exito' | 'peligro' | 'atencion'>

const ALERTA: Record<TonoAlerta, string> = {
  info: 'border-info-border bg-info-soft text-info-fg',
  exito: 'border-exito-border bg-exito-soft text-exito-fg',
  peligro: 'border-peligro-border bg-peligro-soft text-peligro-fg',
  atencion: 'border-atencion-border bg-atencion-soft text-atencion-fg',
}

const ICONO = { info: IconoInfo, exito: IconoExito, peligro: IconoPeligro, atencion: IconoAtencion } as const

export type AlertProps = Omit<ComponentProps<'div'>, 'role' | 'title'> & {
  tono?: TonoAlerta
  titulo?: ReactNode
  /**
   * Rol ARIA. Por defecto ninguno: el aviso es contenido estático.
   * 'alert' solo para el error global que aparece tras una acción; 'status' para confirmaciones dinámicas.
   */
  rol?: 'alert' | 'status'
}

export function Alert({ tono = 'info', titulo, rol, className, children, ...props }: AlertProps) {
  const Icono = ICONO[tono]
  return (
    <div role={rol} className={cx('flex gap-3 rounded-tarjeta border p-4 text-sm', ALERTA[tono], className)} {...props}>
      <Icono className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 space-y-1">
        {titulo ? <p className="font-semibold">{titulo}</p> : null}
        {children ? <div className="text-pretty">{children}</div> : null}
      </div>
    </div>
  )
}
