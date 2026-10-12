'use client'

import { useId, useRef, useSyncExternalStore } from 'react'
import { motion, useReducedMotion } from 'motion/react'
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

/**
 * Cambia el tema revelando el nuevo con un círculo que crece desde `punto` (adaptado de Skiper UI
 * skiper26 — https://skiper-ui.com, atribución requerida por su licencia gratuita). Usa una View
 * Transition con tipo "tema": globals.css (§4) solo anima la raíz con ese tipo, así que no choca con
 * las transiciones de navegación. Sin soporte o con movimiento reducido, el cambio es inmediato.
 */
function cambiarConRevelado(tema: Tema, punto: { x: number; y: number }) {
  const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reducido || typeof document.startViewTransition !== 'function') {
    guardarTema(tema)
    return
  }
  const raiz = document.documentElement
  // Radio hasta la esquina más lejana: el círculo cubre toda la ventana al terminar.
  const radio = Math.hypot(Math.max(punto.x, innerWidth - punto.x), Math.max(punto.y, innerHeight - punto.y))
  raiz.style.setProperty('--tema-x', `${punto.x}px`)
  raiz.style.setProperty('--tema-y', `${punto.y}px`)
  raiz.style.setProperty('--tema-r', `${Math.ceil(radio)}px`)
  try {
    document.startViewTransition({ update: () => guardarTema(tema), types: ['tema'] })
  } catch {
    // Navegadores con View Transitions de nivel 1 (sin tipos): cambio inmediato, sin revelado.
    guardarTema(tema)
  }
}

/**
 * Disco que gira media vuelta al cambiar de tema (adaptado de Skiper UI skiper4, icono 1).
 * Mitad clara y mitad oscura con el color del contexto; solo transform, 350 ms.
 */
function DiscoTema({ oscuro }: { oscuro: boolean }) {
  const reducido = useReducedMotion()
  const transicion = { duration: reducido ? 0 : 0.35, ease: [0.23, 1, 0.32, 1] as const }
  return (
    <svg viewBox="0 0 240 240" aria-hidden="true" className="size-3.5 shrink-0">
      <motion.g animate={{ rotate: oscuro ? -180 : 0 }} transition={transicion} style={{ originX: '120px', originY: '120px' }}>
        <path d="M120 67.5C149.25 67.5 172.5 90.75 172.5 120C172.5 149.25 149.25 172.5 120 172.5" fill="currentColor" />
      </motion.g>
      <motion.path
        animate={{ rotate: oscuro ? 180 : 0 }}
        transition={transicion}
        d="M120 3.75C55.5 3.75 3.75 55.5 3.75 120C3.75 184.5 55.5 236.25 120 236.25C184.5 236.25 236.25 184.5 236.25 120C236.25 55.5 184.5 3.75 120 3.75ZM120 214.5V172.5C90.75 172.5 67.5 149.25 67.5 120C67.5 90.75 90.75 67.5 120 67.5V25.5C172.5 25.5 214.5 67.5 214.5 120C214.5 172.5 172.5 214.5 120 214.5Z"
        fill="currentColor"
      />
    </svg>
  )
}

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
  // Punto del clic: el revelado crece desde ahí. Con teclado no hay puntero y se usa el centro del control.
  const origen = useRef<{ x: number; y: number } | null>(null)

  function elegir(nuevo: Tema, control: HTMLElement) {
    if (nuevo === leerTema()) return
    const caja = control.getBoundingClientRect()
    const punto = origen.current ?? { x: caja.left + caja.width / 2, y: caja.top + caja.height / 2 }
    origen.current = null
    cambiarConRevelado(nuevo, punto)
  }

  return (
    <fieldset className={cx('min-w-0', className)}>
      <legend className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-current/70">
        <DiscoTema oscuro={tema === 'dark'} />
        Tema
      </legend>
      <div className="grid grid-cols-2 gap-0.5 rounded-control border border-current/20 p-0.5">
        {OPCIONES.map((opcion) => {
          const Icono = opcion.valor === 'light' ? IconoSol : IconoLuna
          return (
            <label
              key={opcion.valor}
              onPointerDown={(e) => {
                origen.current = { x: e.clientX, y: e.clientY }
              }}
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
                onChange={(e) => elegir(opcion.valor, e.currentTarget.closest('label') ?? e.currentTarget)}
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
