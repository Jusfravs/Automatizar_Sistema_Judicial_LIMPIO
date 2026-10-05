'use client'

import { useId, useState } from 'react'

const LONGITUD_RESUMEN = 120

export default function DetalleActuacion({ texto }: { texto: string }) {
  const [abierto, setAbierto] = useState(false)
  const id = useId()
  return (
    <div>
      <p id={id} className={`whitespace-pre-line text-sm text-gray-900 ${abierto ? '' : 'line-clamp-2'}`}>
        {texto}
      </p>
      {texto.length > LONGITUD_RESUMEN && (
        <button
          type="button"
          aria-expanded={abierto}
          aria-controls={id}
          onClick={() => setAbierto((v) => !v)}
          className="mt-1 text-xs text-blue-600 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {abierto ? 'Ver menos' : 'Ver más'}
        </button>
      )}
    </div>
  )
}
