import type { ComponentType, ReactNode } from 'react'
import { cx } from '@/lib/cx'

/**
 * Pantalla completa para estados fuera del shell (sin acceso, página inexistente): marca
 * institucional, icono que explica la situación, título serif, texto y acciones. El signo §
 * de fondo enlaza con el login; es solo decorativo.
 */
export function PantallaEstado({
  Icono,
  codigo,
  titulo,
  children,
  acciones,
}: {
  Icono: ComponentType<{ className?: string }>
  /** Rótulo pequeño sobre el título, p. ej. "Error 404". */
  codigo?: string
  titulo: string
  children: ReactNode
  acciones: ReactNode
}) {
  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-bg px-4 py-8 sm:px-6">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-28 -right-8 select-none font-serif text-[22rem] leading-none text-fg/[0.035]"
      >
        §
      </span>
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="h-5 w-1 shrink-0 rounded-full bg-accent" />
        <span className="font-serif text-lg font-semibold tracking-tight text-fg">Gestión Judicial</span>
      </div>
      <div className="relative flex flex-1 items-center justify-center py-10">
        <TarjetaEstado Icono={Icono} codigo={codigo} titulo={titulo} acciones={acciones}>
          {children}
        </TarjetaEstado>
      </div>
    </main>
  )
}

/** Tarjeta del estado; también se usa sola dentro del shell (not-found de una causa o un lote). */
export function TarjetaEstado({
  Icono,
  codigo,
  titulo,
  children,
  acciones,
  className,
}: {
  Icono: ComponentType<{ className?: string }>
  codigo?: string
  titulo: string
  children: ReactNode
  acciones: ReactNode
  className?: string
}) {
  return (
    <div className={cx('animate-subir mx-auto w-full max-w-md rounded-tarjeta bg-surface p-6 text-center shadow-tarjeta sm:p-8', className)}>
      <span aria-hidden="true" className="mx-auto mb-5 grid size-12 place-items-center rounded-full bg-surface-2 text-primary">
        <Icono className="size-6" />
      </span>
      {codigo ? <p className="mb-1 text-rotulo font-semibold uppercase text-muted">{codigo}</p> : null}
      <h1 className="font-serif text-titulo font-semibold text-balance text-fg">{titulo}</h1>
      <div className="mt-3 space-y-2 text-sm text-pretty text-muted">{children}</div>
      <div className="mt-6 flex flex-col-reverse justify-center gap-2 sm:flex-row">{acciones}</div>
    </div>
  )
}
