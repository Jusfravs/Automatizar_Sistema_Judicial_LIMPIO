'use client'

import { useId, useState } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from '@/components/ui/estilos'

const LONGITUD_RESUMEN = 220
const LINEAS_RESUMEN = 3

/**
 * Texto de una actuación. Si es largo se pliega a ~3 líneas; "Ver más" lo despliega animando la
 * altura (.texto-plegable en globals.css; sin soporte, recorta con line-clamp y cambia de golpe).
 * overflow-wrap:anywhere parte identificadores y URLs largos que desbordaban a 375 px.
 */
export default function DetalleActuacion({ texto, destacado = false }: { texto: string; destacado?: boolean }) {
  const [abierto, setAbierto] = useState(false)
  const id = useId()
  const largo = texto.length > LONGITUD_RESUMEN || texto.split('\n').length > LINEAS_RESUMEN
  return (
    <div className="min-w-0">
      <div id={id} className={cx('text-sm', largo && 'texto-plegable')} data-plegado={largo && !abierto ? 'true' : undefined}>
        <p className={cx('whitespace-pre-line text-fg [overflow-wrap:anywhere]', destacado && 'font-medium')}>{texto}</p>
      </div>
      {largo && (
        <button
          type="button"
          aria-expanded={abierto}
          aria-controls={id}
          onClick={() => setAbierto((v) => !v)}
          className={cx('mt-1 rounded-control text-xs font-medium text-primary hover:underline', FOCO)}
        >
          {abierto ? 'Ver menos' : 'Ver más'}
        </button>
      )}
    </div>
  )
}
