'use client'

import { useLinkStatus } from 'next/link'
import { cx } from '@/lib/cx'

/**
 * Flecha de la cabecera ordenable. Va dentro del <Link>: con useLinkStatus responde al clic al
 * instante (gira y se atenúa) mientras llega la tabla ordenada, en vez de esperar al servidor.
 */
export function FlechaOrden({ activa, ascendente }: { activa: boolean; ascendente: boolean }) {
  const { pending } = useLinkStatus()
  // Al pulsar una columna activa, la dirección se invierte: se anticipa el giro.
  const mostrarAscendente = pending && activa ? !ascendente : ascendente
  return (
    <svg
      viewBox="0 0 12 12"
      aria-hidden="true"
      className={cx(
        'size-3 transition-[opacity,rotate] duration-(--duracion-base) ease-salida',
        activa || pending ? 'opacity-100' : 'opacity-0 group-hover/orden:opacity-60',
        pending && 'opacity-60',
        mostrarAscendente && 'rotate-180',
      )}
    >
      <path d="M6 9.5 2.5 5h7z" fill="currentColor" />
    </svg>
  )
}
