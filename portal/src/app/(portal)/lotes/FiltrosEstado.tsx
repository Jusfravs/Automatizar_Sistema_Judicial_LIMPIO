'use client'

import Link from 'next/link'
import { useState, type MouseEvent } from 'react'
import { useReducedMotion, type Transition } from 'motion/react'
import { AnimatedBackground } from '@/components/registro/motion/animated-background'
import { FOCO } from '@/components/ui/estilos'
import { cx } from '@/lib/cx'

export type OpcionEstado = { id: string; etiqueta: string; href: string }

// El fondo del filtro activo se desliza al elegido: resorte sin rebote (un clic no tiene impulso).
const DESLIZAR: Transition = { type: 'spring', duration: 0.24, bounce: 0 }
// Teclado y movimiento reducido: el fondo salta a su sitio.
const SALTAR: Transition = { duration: 0 }

/**
 * Filtros de estado de /lotes. Son enlaces: el activo viene de la URL (`activo`) y lleva
 * aria-current="page". Al pulsar, el fondo se mueve de inmediato (antes de que llegue la página),
 * y cuando la navegación termina `activo` lo confirma.
 */
export function FiltrosEstado({ opciones, activo }: { opciones: readonly OpcionEstado[]; activo: string }) {
  const reducido = useReducedMotion() === true
  const [porTeclado, setPorTeclado] = useState(false)

  // Fase de captura: corre antes que el onClick que AnimatedBackground pone a cada enlace.
  const alPulsar = (e: MouseEvent<HTMLElement>) => {
    // Con modificador se abre en otra pestaña o ventana: esta página no cambia de filtro.
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      e.stopPropagation()
      return
    }
    // detail === 0: lo activó el teclado (Enter). Lo que dispara el teclado no se anima.
    setPorTeclado(e.detail === 0)
  }

  return (
    // isolate: las capas internas (fondo y texto) no compiten con la cabecera fija.
    <nav aria-label="Filtrar por estado" onClickCapture={alPulsar} className="isolate flex flex-wrap gap-2">
      <AnimatedBackground
        defaultValue={activo}
        // z-1: el fondo pasa por encima de los otros filtros al deslizarse y por debajo del texto.
        className="z-1 rounded-full bg-primary"
        transition={reducido || porTeclado ? SALTAR : DESLIZAR}
      >
        {opciones.map((opcion) => (
          <Link
            key={opcion.id}
            data-id={opcion.id}
            href={opcion.href}
            aria-current={opcion.id === activo ? 'page' : undefined}
            className={cx(
              'inline-flex min-h-8 items-center rounded-full border px-3 text-sm font-medium transition-colors duration-(--duracion-lenta) ease-salida',
              FOCO,
              // data-checked lo pone AnimatedBackground: sigue al fondo, no espera a la URL.
              // El texto claro espera a que el fondo llegue: nunca blanco sobre la superficie clara.
              'data-[checked=true]:border-primary data-[checked=true]:text-on-primary data-[checked=true]:delay-(--duracion-rapida)',
              'data-[checked=false]:border-subtle data-[checked=false]:bg-surface data-[checked=false]:text-muted data-[checked=false]:hover:text-fg',
            )}
          >
            {opcion.etiqueta}
          </Link>
        ))}
      </AnimatedBackground>
    </nav>
  )
}
