import Link from 'next/link'
import { ViewTransition, type ReactNode } from 'react'
import { MenuMovil, NavPrincipal } from '@/components/AppShellCliente'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { FOCO } from '@/components/ui/estilos'
import { IconoSalir } from '@/components/ui/iconos'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { cx } from '@/lib/cx'
import { rolEtiqueta } from '@/lib/roles'

export type AppShellProps = {
  nombre: string
  rol: string
  /** Revisiones de IA pendientes; null si no se pudo contar (no se muestra el contador). */
  pendientes: number | null
  children: ReactNode
}

function Marca() {
  return (
    <Link href="/" className={cx('flex items-center gap-2.5 rounded-control', FOCO)}>
      {/* Detalle ámbar: relleno sobre azul (4,59:1), nunca texto ámbar. */}
      <span aria-hidden="true" className="h-5 w-1 shrink-0 rounded-full bg-accent" />
      <span className="font-serif text-lg font-semibold tracking-tight">Gestión Judicial</span>
    </Link>
  )
}

function PieUsuario({ nombre, rol }: { nombre: string; rol: string }) {
  return (
    <div className="space-y-4">
      <div className="min-w-0 space-y-1.5">
        <p className="truncate text-sm font-semibold" title={nombre}>
          {nombre}
        </p>
        <Badge tono="neutral">{rolEtiqueta(rol)}</Badge>
      </div>
      <ThemeToggle />
      <form action="/api/auth/signout" method="POST">
        <Button type="submit" variante="fantasma" tamano="sm" className="w-full border border-current/25">
          <IconoSalir />
          Cerrar sesión
        </Button>
      </form>
    </div>
  )
}

/**
 * Estructura de las pantallas autenticadas: barra lateral fija de 248px en lg+ y cabecera con
 * menú desplegable en móvil. Dentro de la barra azul el anillo de foco pasa a on-nav
 * (--focus redefinido localmente), porque el foco azul no contrasta sobre azul.
 */
export function AppShell({ nombre, rol, pendientes, children }: AppShellProps) {
  const pie = <PieUsuario nombre={nombre} rol={rol} />
  return (
    <div className="flex-1 lg:pl-62">
      <a
        href="#contenido"
        className={cx(
          'sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-(--z-aviso) focus:rounded-control focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary focus:shadow-elevada',
          FOCO,
        )}
      >
        Saltar al contenido
      </a>

      <aside className="fixed inset-y-0 left-0 z-(--z-cabecera) hidden w-62 flex-col bg-nav text-on-nav lg:flex [--focus:var(--on-nav)]">
        <div className="flex h-16 shrink-0 items-center px-5">
          <Marca />
        </div>
        <NavPrincipal pendientes={pendientes} className="flex-1 overflow-y-auto px-3 py-2" />
        <div className="shrink-0 border-t border-on-nav/15 p-4">{pie}</div>
      </aside>

      <MenuMovil marca={<Marca />} pie={pie} pendientes={pendientes} />

      <main id="contenido" tabIndex={-1} className="mx-auto w-full max-w-7xl px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
        {/*
          Transición entre pantallas. El shell vive en el layout de (portal), así que este límite
          persiste: cada navegación, carga (Suspense) o refresco que cambia el contenido es un "update"
          con fundido corto. Las secciones de una pantalla recién montada además suben escalonadas.
        */}
        <ViewTransition update="pagina" default="none">
          <div className="entrada-pagina">{children}</div>
        </ViewTransition>
      </main>
    </div>
  )
}
