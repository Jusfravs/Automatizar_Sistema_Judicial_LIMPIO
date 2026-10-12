'use client'

import { useReducedMotion } from 'motion/react'
import { TextShimmer } from '@/components/registro/motion/text-shimmer'
import { useHidratado } from '@/lib/hidratado'
import { cx } from '@/lib/cx'

/**
 * Mensaje de espera con un brillo que lo recorre (motion-primitives TextShimmer). Es un indicador
 * de carga, no anima ninguna acción. Con movimiento reducido el texto queda estático en `muted`.
 *
 * Hasta hidratar se pinta estático: `useReducedMotion` lee la preferencia en el primer render del
 * cliente y no coincide con el del servidor. El brillo parte del mismo color, así que el relevo no
 * se nota. El texto sigue siendo un nodo de texto: lo leen los lectores salvo que el contenedor
 * lo oculte con aria-hidden.
 */
export function TextoCargando({ children, className }: { children: string; className?: string }) {
  const reducido = useReducedMotion() === true
  const hidratado = useHidratado()

  if (!hidratado || reducido) {
    return <span className={cx('inline-block text-muted', className)}>{children}</span>
  }
  return (
    <TextShimmer as="span" className={className}>
      {children}
    </TextShimmer>
  )
}
