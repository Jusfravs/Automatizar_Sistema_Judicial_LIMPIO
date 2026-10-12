'use client'

import { useState } from 'react'
import { useReducedMotion } from 'motion/react'
import { BorderTrail } from '@/components/registro/motion/border-trail'
import { useHidratado } from '@/lib/hidratado'

// Tres vueltas lentas y se retira: avisa de trabajo vivo al llegar sin ser un bucle permanente
// (WCAG 2.2.2). El refresco de Inicio no lo reinicia: el componente persiste entre refrescos.
const VUELTA_S = 8
const VUELTAS = 3

/**
 * Trazo que recorre el borde de "Lotes en curso" mientras el servidor procesa un lote. Lento y
 * tenue para no competir con el contenido. Decorativo (aria-hidden); con movimiento reducido no se
 * muestra: el estado ya lo dicen la insignia y la barra de avance. El padre debe tener
 * `position: relative`.
 */
export function TrazoEnCurso() {
  const reducido = useReducedMotion()
  const [terminado, setTerminado] = useState(false)
  // useReducedMotion difiere entre servidor y cliente: el trazo se monta tras hidratar.
  const hidratado = useHidratado()
  if (!hidratado || reducido || terminado) return null
  return (
    <div aria-hidden="true" className="contents">
      <BorderTrail
        size={96}
        className="bg-progreso-solid opacity-70"
        transition={{ repeat: VUELTAS - 1, duration: VUELTA_S, ease: 'linear' }}
        onAnimationComplete={() => setTerminado(true)}
      />
    </div>
  )
}
