'use client'

import { useEffect, useId, useRef, type ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from './estilos'
import { IconoCerrar } from './iconos'

export type DialogProps = {
  abierto: boolean
  /** Se llama al pedir el cierre (Escape, botón Cerrar o clic en el telón). El padre pone `abierto` en false. */
  alCerrar: () => void
  titulo: ReactNode
  descripcion?: ReactNode
  children?: ReactNode
  /** Botones del pie, alineados a la derecha. La acción principal va al final. */
  acciones?: ReactNode
  className?: string
}

/**
 * Modal sobre <dialog> nativo con showModal(): trampa de foco, Escape y capa superior los da el navegador.
 * Al cerrarse devuelve el foco al elemento que lo abrió. La entrada se anima con @starting-style
 * y reduced-motion la anula (globals.css).
 */
export function Dialog({ abierto, alCerrar, titulo, descripcion, children, acciones, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const disparador = useRef<HTMLElement | null>(null)
  const cierrePorProp = useRef(false)
  const alCerrarRef = useRef(alCerrar)
  const tituloId = useId()
  const descripcionId = useId()

  useEffect(() => {
    alCerrarRef.current = alCerrar
  }, [alCerrar])

  useEffect(() => {
    const dialogo = ref.current
    if (!dialogo) return
    if (abierto && !dialogo.open) {
      disparador.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      dialogo.showModal()
    } else if (!abierto && dialogo.open) {
      cierrePorProp.current = true
      dialogo.close()
    }
  }, [abierto])

  // Evento nativo `close`: llega tanto si cerró el padre como si el navegador cerró con Escape.
  function alCerrarNativo() {
    const porProp = cierrePorProp.current
    cierrePorProp.current = false
    const previo = disparador.current
    disparador.current = null
    if (previo?.isConnected) previo.focus()
    if (!porProp) alCerrarRef.current()
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={tituloId}
      aria-describedby={descripcion ? descripcionId : undefined}
      onClose={alCerrarNativo}
      onCancel={(e) => {
        // Escape: el padre decide; cerramos vía `abierto` para mantener el control.
        e.preventDefault()
        alCerrarRef.current()
      }}
      onClick={(e) => {
        // El <dialog> solo recibe el clic directo en el margen exterior (el telón visible).
        if (e.target === e.currentTarget) alCerrarRef.current()
      }}
      className={cx(
        'm-auto w-full max-w-lg bg-transparent p-4 text-fg backdrop:bg-velo',
        'transition duration-(--duracion-lenta) ease-salida starting:open:scale-95 starting:open:opacity-0',
        className,
      )}
    >
      <div className="overflow-hidden rounded-modal bg-surface shadow-overlay">
        <div className="flex items-start justify-between gap-4 px-6 pt-5">
          <h2 id={tituloId} className="text-lg font-semibold text-fg text-balance">
            {titulo}
          </h2>
          <button
            type="button"
            onClick={() => alCerrarRef.current()}
            className={cx(
              'grid size-8 shrink-0 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-fg',
              FOCO,
            )}
          >
            <IconoCerrar />
            <span className="sr-only">Cerrar</span>
          </button>
        </div>
        {descripcion ? (
          <p id={descripcionId} className="px-6 pt-1 text-sm text-muted text-pretty">
            {descripcion}
          </p>
        ) : null}
        <div className="px-6 py-4 text-sm">{children}</div>
        {acciones ? (
          <div className="flex flex-wrap justify-end gap-2 border-t border-subtle bg-surface-2 px-6 py-3">{acciones}</div>
        ) : null}
      </div>
    </dialog>
  )
}
