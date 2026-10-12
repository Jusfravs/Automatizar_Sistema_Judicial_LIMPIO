'use client'

import { motion, useReducedMotion, useScroll, type SpringOptions } from 'motion/react'
import { ScrollProgress } from '@/components/registro/motion/scroll-progress'
import { useHidratado } from '@/lib/hidratado'

const BARRA = 'h-0.5 origin-left bg-primary'

// Al volver con Atrás o recargar, el navegador restaura el scroll: ese primer salto no se anima
// (motion lee skipInitialAnimation del resorte aunque SpringOptions no lo declare).
const RESORTE: SpringOptions & { skipInitialAnimation: boolean } = { skipInitialAnimation: true }

/**
 * Barra fina que indica cuánto del expediente se ha leído. Decorativa (aria-hidden): no se
 * interactúa con ella. Va fija arriba del área de contenido: bajo la cabecera móvil (56px) y, en
 * escritorio, a la derecha de la barra lateral (248px). z-1: sobre el contenido, bajo la cabecera
 * y su menú desplegable.
 */
export function ProgresoLectura() {
  const reducido = useReducedMotion() === true
  // useReducedMotion difiere entre servidor y cliente: la barra se monta tras hidratar.
  const hidratado = useHidratado()
  if (!hidratado) return null
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-14 z-1 lg:left-62 lg:top-0">
      {reducido ? <BarraDirecta /> : <ScrollProgress className={BARRA} springOptions={RESORTE} />}
    </div>
  )
}

/** Movimiento reducido: la barra sigue al scroll tal cual, sin la inercia del resorte. */
function BarraDirecta() {
  const { scrollYProgress } = useScroll()
  return <motion.div className={BARRA} style={{ scaleX: scrollYProgress }} />
}
