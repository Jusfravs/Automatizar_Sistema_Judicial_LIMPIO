'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useId, useRef, useState, type ComponentType, type FocusEvent, type MouseEvent, type ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from '@/components/ui/estilos'
import { IconoCasos, IconoCerrar, IconoInicio, IconoLotes, IconoMenu } from '@/components/ui/iconos'

type Enlace = {
  href: string
  etiqueta: string
  Icono: ComponentType<{ className?: string }>
  conPendientes?: boolean
}

const ENLACES: readonly Enlace[] = [
  { href: '/inicio', etiqueta: 'Inicio', Icono: IconoInicio },
  { href: '/lotes', etiqueta: 'Lotes', Icono: IconoLotes },
  { href: '/casos', etiqueta: 'Casos', Icono: IconoCasos, conPendientes: true },
]

function estaActivo(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`)
}

function ContadorPendientes({ n }: { n: number }) {
  const texto = n === 1 ? '1 revisión pendiente' : `${n} revisiones pendientes`
  return (
    <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-xs font-semibold text-on-accent tabular-nums">
      <span aria-hidden="true">{n > 99 ? '99+' : n}</span>
      <span className="sr-only">{texto}</span>
    </span>
  )
}

/**
 * Menú principal. Va sobre la barra (bg-nav): hereda text-on-nav.
 * Ítem activo = aria-current + barra ámbar + fondo + peso (el ámbar nunca es la única señal).
 */
export function NavPrincipal({ pendientes, className }: { pendientes: number | null; className?: string }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Navegación principal" className={className}>
      <ul className="space-y-0.5">
        {ENLACES.map(({ href, etiqueta, Icono, conPendientes }) => {
          const activo = estaActivo(pathname, href)
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={activo ? 'page' : undefined}
                className={cx(
                  'relative flex h-9 items-center gap-3 rounded-control px-3 text-sm transition-colors',
                  FOCO,
                  activo ? 'bg-on-nav/15 font-semibold' : 'font-medium text-on-nav/85 hover:bg-on-nav/10 hover:text-on-nav',
                )}
              >
                {activo ? (
                  <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-0.75 rounded-full bg-(--nav-indicador)" />
                ) : null}
                <Icono className="size-4 shrink-0" />
                <span className="truncate">{etiqueta}</span>
                {conPendientes && pendientes ? <ContadorPendientes n={pendientes} /> : null}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

/**
 * Cabecera móvil (< lg) con botón de menú que despliega el mismo contenido que la barra lateral.
 * El panel se cierra al navegar (se abre "para" una ruta), con Escape, al pulsar un enlace
 * y cuando el foco sale de la cabecera.
 */
export function MenuMovil({ marca, pie, pendientes }: { marca: ReactNode; pie: ReactNode; pendientes: number | null }) {
  const pathname = usePathname()
  const [rutaAbierta, setRutaAbierta] = useState<string | null>(null)
  const abierto = rutaAbierta === pathname
  const botonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!abierto) return
    function alTeclear(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setRutaAbierta(null)
        botonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', alTeclear)
    return () => document.removeEventListener('keydown', alTeclear)
  }, [abierto])

  function alSalirFoco(e: FocusEvent<HTMLElement>) {
    const destino = e.relatedTarget
    if (abierto && destino instanceof Node && !e.currentTarget.contains(destino)) setRutaAbierta(null)
  }

  function alPulsarPanel(e: MouseEvent<HTMLDivElement>) {
    if (e.target instanceof Element && e.target.closest('a')) setRutaAbierta(null)
  }

  return (
    <header
      onBlur={alSalirFoco}
      className="sticky top-0 z-(--z-cabecera) bg-nav text-on-nav lg:hidden [--focus:var(--on-nav)]"
    >
      <div className="flex h-14 items-center justify-between gap-3 px-4">
        {marca}
        <button
          ref={botonRef}
          type="button"
          aria-expanded={abierto}
          aria-controls={panelId}
          onClick={() => setRutaAbierta(abierto ? null : pathname)}
          className={cx('grid size-10 place-items-center rounded-control transition-colors hover:bg-on-nav/10', FOCO)}
        >
          {abierto ? <IconoCerrar className="size-5" /> : <IconoMenu className="size-5" />}
          <span className="sr-only">Menú</span>
        </button>
      </div>
      <div
        id={panelId}
        hidden={!abierto}
        onClick={alPulsarPanel}
        className="fixed inset-x-0 top-14 bottom-0 overflow-y-auto border-t border-on-nav/15 bg-nav transition duration-(--duracion-base) ease-salida starting:-translate-y-1 starting:opacity-0"
      >
        <div className="space-y-6 px-4 py-4">
          <NavPrincipal pendientes={pendientes} />
          <div className="border-t border-on-nav/15 pt-4">{pie}</div>
        </div>
      </div>
    </header>
  )
}
