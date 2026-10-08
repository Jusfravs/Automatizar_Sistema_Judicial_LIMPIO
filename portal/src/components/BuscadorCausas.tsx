'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { createClient } from '@/lib/supabase/client'
import { cx } from '@/lib/cx'
import { NAVEGACION } from '@/lib/transiciones'
import { Dialog } from '@/components/ui/Dialog'
import { EstadoBadge } from '@/components/ui/EstadoBadge'
import { CONTROL, FOCO } from '@/components/ui/estilos'
import { IconoBuscar, Spinner } from '@/components/ui/iconos'

/** Evento para abrir el buscador desde cualquier botón (barra lateral, cabecera móvil). */
export const EVENTO_ABRIR_BUSCADOR = 'buscador-causas:abrir'

const MINIMO_CARACTERES = 2
const MAXIMO_RESULTADOS = 8
const ESPERA_MS = 180

type Resultado = {
  numero_causa: string
  estado: string | null
  fase_actual: string | null
  actor: string | null
  demandado: string | null
}

/**
 * Texto seguro para el filtro `or` de PostgREST: sin comodines propios (% _) ni separadores
 * de su sintaxis (, ( ) * \ "). El número de causa solo usa dígitos, letras y guiones.
 */
function limpiar(texto: string): string {
  return texto.replace(/[%_,()*\\"]/g, ' ').replace(/\s+/g, ' ').trim()
}

function partes(r: Resultado): string {
  return [r.actor, r.demandado].filter(Boolean).join(' contra ')
}

/** Botón que abre el buscador. "barra" va en la barra lateral azul; "icono", en la cabecera móvil. */
export function BotonBuscarCausa({ variante }: { variante: 'barra' | 'icono' }) {
  const abrir = () => window.dispatchEvent(new Event(EVENTO_ABRIR_BUSCADOR))
  if (variante === 'icono') {
    return (
      <button
        type="button"
        onClick={abrir}
        className={cx('grid size-10 place-items-center rounded-control transition-colors hover:bg-on-nav/10', FOCO)}
      >
        <IconoBuscar className="size-5" />
        <span className="sr-only">Buscar causa</span>
      </button>
    )
  }
  return (
    <button
      type="button"
      onClick={abrir}
      aria-keyshortcuts="Control+K Meta+K"
      className={cx(
        'flex h-9 w-full items-center gap-2.5 rounded-control border border-on-nav/20 bg-on-nav/5 px-3 text-sm text-on-nav/80 transition-colors hover:border-on-nav/35 hover:bg-on-nav/10 hover:text-on-nav',
        FOCO,
      )}
    >
      <IconoBuscar className="size-4 shrink-0" />
      <span className="flex-1 text-left">Buscar causa</span>
      <kbd aria-hidden="true" className="rounded-sm border border-on-nav/25 px-1.5 font-sans text-rotulo text-on-nav/70">
        Ctrl K
      </kbd>
    </button>
  )
}

type Estado = 'inactivo' | 'buscando' | 'listo' | 'error'

/**
 * Búsqueda global de causas (Ctrl/⌘+K; sin atajos de una sola tecla, WCAG 2.1.4). Busca por número
 * de causa, actor o demandado y abre el detalle. Patrón combobox de ARIA: el foco queda en el campo y las flechas mueven la opción
 * activa (aria-activedescendant). Se monta una sola vez, en el shell.
 */
export function BuscadorCausas() {
  const router = useRouter()
  const supabase = useMemo(() => createClient(), [])
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const [resultados, setResultados] = useState<Resultado[]>([])
  const [estado, setEstado] = useState<Estado>('inactivo')
  const [activo, setActivo] = useState(0)
  const campo = useRef<HTMLInputElement>(null)
  const consulta = useRef(0)
  const listaId = useId()
  const ayudaId = useId()

  const termino = limpiar(texto)
  const suficiente = termino.length >= MINIMO_CARACTERES

  // Atajo global con modificador: Ctrl/⌘+K.
  useEffect(() => {
    function alTeclear(e: globalThis.KeyboardEvent) {
      if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey) && !e.altKey) {
        e.preventDefault()
        setAbierto(true)
      }
    }
    const alPedir = () => setAbierto(true)
    document.addEventListener('keydown', alTeclear)
    window.addEventListener(EVENTO_ABRIR_BUSCADOR, alPedir)
    return () => {
      document.removeEventListener('keydown', alTeclear)
      window.removeEventListener(EVENTO_ABRIR_BUSCADOR, alPedir)
    }
  }, [])

  // La opción activa siempre visible al moverse con las flechas.
  useEffect(() => {
    if (!abierto) return
    document.getElementById(`${listaId}-op-${activo}`)?.scrollIntoView({ block: 'nearest' })
  }, [abierto, activo, listaId])

  // showModal enfoca el primer control (el botón Cerrar): llevamos el foco al campo.
  useEffect(() => {
    if (!abierto) return
    const marco = requestAnimationFrame(() => campo.current?.select())
    return () => cancelAnimationFrame(marco)
  }, [abierto])

  useEffect(() => {
    if (!abierto || !suficiente) return
    const id = ++consulta.current
    const espera = setTimeout(async () => {
      setEstado('buscando')
      const patron = `%${termino}%`
      const { data, error } = await supabase
        .from('expedientes')
        .select('numero_causa, estado, fase_actual, actor, demandado')
        .or(`numero_causa.ilike.${patron},actor.ilike.${patron},demandado.ilike.${patron}`)
        .order('actualizado_en', { ascending: false })
        .limit(MAXIMO_RESULTADOS)
      if (id !== consulta.current) return // llegó tarde: ya hay una búsqueda más nueva
      if (error) {
        console.error('No se pudo buscar causas:', error.message)
        setEstado('error')
        return
      }
      setResultados(data ?? [])
      setActivo(0)
      setEstado('listo')
    }, ESPERA_MS)
    return () => clearTimeout(espera)
  }, [abierto, suficiente, termino, supabase])

  function abrirCausa(numero: string) {
    setAbierto(false)
    setTexto('')
    setResultados([])
    setEstado('inactivo')
    router.push(`/casos/${encodeURIComponent(numero)}`, { transitionTypes: NAVEGACION })
  }

  function alTeclearCampo(e: KeyboardEvent<HTMLInputElement>) {
    if (!resultados.length || !suficiente) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActivo((i) => (i + 1) % resultados.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActivo((i) => (i - 1 + resultados.length) % resultados.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const elegido = resultados[activo]
      if (elegido) abrirCausa(elegido.numero_causa)
    }
  }

  const visibles = suficiente ? resultados : []
  const opcionId = (i: number) => `${listaId}-op-${i}`
  const mostrarLista = suficiente && estado !== 'error' && visibles.length > 0

  let mensaje: string
  if (!suficiente) mensaje = 'Escribe al menos 2 caracteres: número de causa, actor o demandado.'
  else if (estado === 'error') mensaje = 'No se pudo completar la búsqueda. Revisa tu conexión e inténtalo de nuevo.'
  else if (estado === 'listo' && visibles.length === 0) mensaje = `No hay causas que coincidan con «${termino}».`
  else if (estado === 'listo' && visibles.length >= MAXIMO_RESULTADOS)
    mensaje = `Se muestran las ${MAXIMO_RESULTADOS} más recientes. Escribe más para afinar la búsqueda.`
  else if (estado === 'listo') mensaje = visibles.length === 1 ? '1 causa encontrada.' : `${visibles.length} causas encontradas.`
  else mensaje = 'Buscando…'

  return (
    <Dialog abierto={abierto} alCerrar={() => setAbierto(false)} titulo="Buscar causa" ancho="amplio" animado={false} className="mt-[12vh]">
      <div className="-mx-6 -mb-4 -mt-1">
        <div className="relative px-6 pb-3">
          <IconoBuscar className="pointer-events-none absolute left-9 top-[calc(50%-6px)] size-4 -translate-y-1/2 text-muted" />
          <input
            ref={campo}
            type="text"
            inputMode="search"
            enterKeyHint="go"
            role="combobox"
            aria-label="Buscar causa"
            aria-expanded={mostrarLista}
            aria-controls={listaId}
            aria-activedescendant={mostrarLista ? opcionId(activo) : undefined}
            aria-autocomplete="list"
            aria-describedby={ayudaId}
            autoComplete="off"
            spellCheck={false}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={alTeclearCampo}
            placeholder="Número de causa, actor o demandado"
            className={cx(CONTROL, 'h-11 pl-9 pr-9 text-base')}
          />
          {estado === 'buscando' && suficiente ? (
            <Spinner className="absolute right-9 top-[calc(50%-6px)] size-4 -translate-y-1/2 animate-spin text-muted" />
          ) : null}
        </div>

        <p id={ayudaId} role="status" className="px-6 pb-2 text-xs text-muted">
          {mensaje}
        </p>

        <ul
          id={listaId}
          role="listbox"
          aria-label="Causas encontradas"
          hidden={!mostrarLista}
          className="max-h-[50vh] overflow-y-auto border-t border-subtle py-1.5"
        >
          {visibles.map((r, i) => (
            <li
              key={r.numero_causa}
              id={opcionId(i)}
              role="option"
              aria-selected={i === activo}
              onMouseMove={() => setActivo(i)}
              onClick={() => abrirCausa(r.numero_causa)}
              className={cx(
                // Sin transición: el resaltado lo mueven las flechas y debe ser instantáneo.
                'mx-1.5 flex cursor-pointer items-center gap-3 rounded-control px-4.5 py-2.5',
                i === activo && 'bg-surface-2',
              )}
            >
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="font-mono text-sm font-semibold tracking-tight text-fg">{r.numero_causa}</p>
                {/* Las partes van en su propia línea: suelen ser el dato que se buscó. */}
                {partes(r) ? (
                  <p className="line-clamp-2 text-xs text-fg [overflow-wrap:anywhere]">{partes(r)}</p>
                ) : null}
                <p className="truncate text-xs text-muted">{r.fase_actual ?? 'Sin clasificación todavía'}</p>
              </div>
              {r.estado ? <EstadoBadge tipo="caso" estado={r.estado} /> : null}
            </li>
          ))}
        </ul>

        <div
          aria-hidden="true"
          className="flex flex-wrap gap-x-4 gap-y-1 border-t border-subtle bg-surface-2 px-6 py-2.5 text-xs text-muted"
        >
          <span>
            <kbd className="font-sans font-semibold text-fg">↑ ↓</kbd> moverse
          </span>
          <span>
            <kbd className="font-sans font-semibold text-fg">Enter</kbd> abrir
          </span>
          <span>
            <kbd className="font-sans font-semibold text-fg">Esc</kbd> cerrar
          </span>
        </div>
      </div>
    </Dialog>
  )
}
