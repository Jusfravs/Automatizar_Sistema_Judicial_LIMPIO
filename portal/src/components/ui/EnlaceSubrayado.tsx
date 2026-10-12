import Link from 'next/link'
import type { ComponentProps } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from './estilos'

/**
 * Enlace con un subrayado que crece desde la izquierda al pasar el puntero y se recoge al salir
 * (origen fijo: se puede interrumpir sin saltos). Solo `transform` (scaleX) sobre un ::before de 1px
 * en el color del texto. Entrada --duracion-lenta; salida más corta (--duracion-base). `hover:` de Tailwind 4 ya se limita a
 * dispositivos con puntero, y con movimiento reducido no hay transición.
 *
 * Adaptado de Skiper UI, skiper40 `Link000` (https://skiper-ui.com), por @gurvinder-singh02.
 * Licencia gratuita de Skiper UI: uso y modificación permitidos con atribución a Skiper UI.
 */
export function EnlaceSubrayado({ className, ...props }: ComponentProps<typeof Link>) {
  return (
    <Link
      {...props}
      className={cx(
        'relative inline-flex items-center rounded-control',
        "before:pointer-events-none before:absolute before:inset-x-0 before:bottom-0 before:h-px before:bg-current before:content-['']",
        'before:origin-left before:scale-x-0 before:transition-transform before:duration-(--duracion-base) before:ease-salida',
        'hover:before:scale-x-100 hover:before:duration-(--duracion-lenta) focus-visible:before:scale-x-100',
        'motion-reduce:before:transition-none',
        FOCO,
        className,
      )}
    />
  )
}
