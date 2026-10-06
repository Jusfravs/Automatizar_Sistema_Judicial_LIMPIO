'use client'

import { useId, useState } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from '@/components/ui/estilos'

const LONGITUD_RESUMEN = 120

export default function DetalleActuacion({ texto }: { texto: string }) {
  const [abierto, setAbierto] = useState(false)
  const id = useId()
  return (
    <div>
      <p id={id} className={cx('whitespace-pre-line text-sm text-fg', !abierto && 'line-clamp-2')}>
        {texto}
      </p>
      {texto.length > LONGITUD_RESUMEN && (
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
