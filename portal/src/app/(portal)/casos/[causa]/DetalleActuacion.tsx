'use client'

import { useId, useState } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from '@/components/ui/estilos'

const LONGITUD_RESUMEN = 220
const LINEAS_RESUMEN = 3

export default function DetalleActuacion({ texto, destacado = false }: { texto: string; destacado?: boolean }) {
  const [abierto, setAbierto] = useState(false)
  const id = useId()
  return (
    <div>
      <p id={id} className={cx('whitespace-pre-line text-sm text-fg', destacado && 'font-medium', !abierto && 'line-clamp-3')}>
        {texto}
      </p>
      {(texto.length > LONGITUD_RESUMEN || texto.split('\n').length > LINEAS_RESUMEN) && (
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
