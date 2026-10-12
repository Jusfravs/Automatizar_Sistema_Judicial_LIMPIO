'use client'

import { useReducedMotion } from 'motion/react'
import { BorderTrail } from '@/components/registro/motion/border-trail'

/**
 * Trazo que recorre el borde de "Lotes en curso" mientras el servidor procesa un lote: señal de
 * trabajo vivo, lenta y tenue para no competir con el contenido. Decorativo (aria-hidden) y sin
 * movimiento reducido no se muestra: el estado ya lo dicen la insignia y la barra de avance.
 * El padre debe tener `position: relative`.
 */
export function TrazoEnCurso() {
  const reducido = useReducedMotion()
  if (reducido) return null
  return (
    <div aria-hidden="true" className="contents">
      <BorderTrail size={96} className="bg-progreso-solid opacity-70" transition={{ repeat: Infinity, duration: 8, ease: 'linear' }} />
    </div>
  )
}
