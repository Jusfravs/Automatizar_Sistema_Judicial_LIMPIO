'use client'

import { useId, useSyncExternalStore } from 'react'
import { cx } from '@/lib/cx'

export type Tema = 'light' | 'dark' | 'system'

const CLAVE = 'tema'

const OPCIONES: readonly { valor: Tema; etiqueta: string }[] = [
  { valor: 'light', etiqueta: 'Claro' },
  { valor: 'dark', etiqueta: 'Oscuro' },
  { valor: 'system', etiqueta: 'Sistema' },
]

// Almacén externo: localStorage + oyentes de este módulo (todas las instancias se sincronizan).
const oyentes = new Set<() => void>()

function leerTema(): Tema {
  try {
    const valor = window.localStorage.getItem(CLAVE)
    return valor === 'light' || valor === 'dark' ? valor : 'system'
  } catch {
    return 'system'
  }
}

/** Misma regla que el script inline de layout.tsx: light/dark fijan data-theme; system lo quita. */
function aplicarTema(tema: Tema) {
  const raiz = document.documentElement
  if (tema === 'system') delete raiz.dataset.theme
  else raiz.dataset.theme = tema
}

function guardarTema(tema: Tema) {
  try {
    window.localStorage.setItem(CLAVE, tema)
  } catch {
    // Almacenamiento bloqueado (modo privado, política): el tema se aplica solo a esta pestaña.
  }
  aplicarTema(tema)
  oyentes.forEach((avisar) => avisar())
}

function suscribir(avisar: () => void) {
  oyentes.add(avisar)
  // Otra pestaña cambió el tema.
  function alAlmacenar(e: StorageEvent) {
    if (e.key === CLAVE || e.key === null) {
      aplicarTema(leerTema())
      avisar()
    }
  }
  window.addEventListener('storage', alAlmacenar)
  return () => {
    oyentes.delete(avisar)
    window.removeEventListener('storage', alAlmacenar)
  }
}

// En el servidor no hay preferencia: se pinta "Sistema" y React corrige tras hidratar, sin desajuste.
const temaServidor = (): Tema => 'system'

/**
 * Selector Claro / Oscuro / Sistema como grupo de radios (teclado nativo: flechas entre opciones).
 * Hereda el color del contexto (currentColor), así que sirve sobre surface y sobre la barra azul.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const tema = useSyncExternalStore(suscribir, leerTema, temaServidor)
  const nombre = useId()

  return (
    <fieldset className={cx('min-w-0', className)}>
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide">Tema</legend>
      <div className="grid grid-cols-3 gap-0.5 rounded-control border border-current/25 p-0.5">
        {OPCIONES.map((opcion) => (
          <label
            key={opcion.valor}
            className={cx(
              // rounded-sm (4px) = radio de control (6px) − relleno (2px): radio concéntrico.
              'flex h-7 cursor-pointer items-center justify-center rounded-sm text-xs font-medium transition-colors',
              'hover:bg-current/10 has-[:checked]:bg-current/15 has-[:checked]:font-semibold',
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
            {opcion.etiqueta}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
