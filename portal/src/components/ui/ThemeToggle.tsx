'use client'

import { useId, useSyncExternalStore } from 'react'
import { cx } from '@/lib/cx'

export type Tema = 'light' | 'dark'

const CLAVE = 'tema'
const CONSULTA_OSCURO = '(prefers-color-scheme: dark)'

const OPCIONES: readonly { valor: Tema; etiqueta: string }[] = [
  { valor: 'light', etiqueta: 'Claro' },
  { valor: 'dark', etiqueta: 'Oscuro' },
]

// Almacén externo: localStorage + preferencia del sistema + oyentes de este módulo.
const oyentes = new Set<() => void>()

function temaGuardado(): Tema | null {
  try {
    const valor = window.localStorage.getItem(CLAVE)
    return valor === 'light' || valor === 'dark' ? valor : null
  } catch {
    return null
  }
}

/** Tema efectivo: la elección guardada o, si nunca se eligió, el del sistema operativo. */
function leerTema(): Tema {
  return temaGuardado() ?? (window.matchMedia(CONSULTA_OSCURO).matches ? 'dark' : 'light')
}

/** Misma regla que el script inline de layout.tsx: data-theme fija el tema elegido. */
function guardarTema(tema: Tema) {
  try {
    window.localStorage.setItem(CLAVE, tema)
  } catch {
    // Almacenamiento bloqueado (modo privado, política): el tema se aplica solo a esta pestaña.
  }
  document.documentElement.dataset.theme = tema
  oyentes.forEach((avisar) => avisar())
}

function suscribir(avisar: () => void) {
  oyentes.add(avisar)
  // Otra pestaña cambió el tema.
  function alAlmacenar(e: StorageEvent) {
    if (e.key === CLAVE || e.key === null) {
      const tema = temaGuardado()
      if (tema) document.documentElement.dataset.theme = tema
      else delete document.documentElement.dataset.theme
      avisar()
    }
  }
  // Sin elección guardada, el selector sigue al sistema si este cambia (p. ej. modo noche automático).
  const consulta = window.matchMedia(CONSULTA_OSCURO)
  window.addEventListener('storage', alAlmacenar)
  consulta.addEventListener('change', avisar)
  return () => {
    oyentes.delete(avisar)
    window.removeEventListener('storage', alAlmacenar)
    consulta.removeEventListener('change', avisar)
  }
}

// En el servidor no hay preferencia: se pinta "Claro" y React corrige tras hidratar.
const temaServidor = (): Tema => 'light'

function IconoSol({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden="true" className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  )
}

function IconoLuna({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" />
    </svg>
  )
}

/**
 * Selector Claro / Oscuro como grupo de radios (teclado nativo: flechas entre opciones). Mientras
 * no se elige, marca el tema del sistema operativo. Misma tipografía y resaltado que la navegación
 * principal; hereda el color del contexto, así que sirve sobre surface y sobre la barra azul.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const tema = useSyncExternalStore(suscribir, leerTema, temaServidor)
  const nombre = useId()

  return (
    <fieldset className={cx('min-w-0', className)}>
      <legend className="mb-1.5 text-xs font-medium text-current/70">Tema</legend>
      <div className="grid grid-cols-2 gap-0.5 rounded-control border border-current/20 p-0.5">
        {OPCIONES.map((opcion) => {
          const Icono = opcion.valor === 'light' ? IconoSol : IconoLuna
          return (
            <label
              key={opcion.valor}
              className={cx(
                // rounded-sm (4px) = radio de control (6px) − relleno (2px): radio concéntrico.
                'flex h-8 cursor-pointer items-center justify-center gap-2 rounded-sm text-sm font-medium text-current/85 transition-colors',
                'hover:bg-current/10 hover:text-current has-[:checked]:bg-current/15 has-[:checked]:font-semibold has-[:checked]:text-current',
                'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus',
              )}
            >
              <input
                type="radio"
                name={nombre}
                value={opcion.valor}
                checked={tema === opcion.valor}
                onChange={() => guardarTema(opcion.valor)}
                className="sr-only"
              />
              <Icono className="size-4 shrink-0" />
              {opcion.etiqueta}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
