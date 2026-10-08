'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useRef, useState, useTransition, type FormEvent, type ReactNode } from 'react'
import { Checkbox } from '@/components/ui/Checkbox'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { cx } from '@/lib/cx'
import { clasesBoton } from '@/components/ui/estilos'

export type ValoresFiltro = {
  q: string
  estado: string
  fase: string
  ciudad: string
  pendientes: boolean
  orden: string
}

// Texto: espera breve para no consultar en cada tecla. Selects y casilla: inmediato.
const ESPERA_TEXTO_MS = 300

function construirUrl(ruta: string, v: ValoresFiltro): string {
  const sp = new URLSearchParams()
  if (v.q.trim()) sp.set('q', v.q.trim())
  if (v.estado) sp.set('estado', v.estado)
  if (v.fase) sp.set('fase', v.fase)
  if (v.ciudad.trim()) sp.set('ciudad', v.ciudad.trim())
  if (v.pendientes) sp.set('pendientes', '1')
  if (v.orden) sp.set('orden', v.orden)
  const consulta = sp.toString()
  return consulta ? `${ruta}?${consulta}` : ruta
}

/**
 * Filtros de casos que se aplican solos y zona de resultados. Mientras llega la nueva lista, la
 * anterior se queda visible y atenuada con una barra fina de progreso (en vez de un esqueleto que
 * borra el contexto). El foco nunca sale del campo en el que se escribe.
 * Sin JavaScript sigue funcionando como formulario GET con su botón.
 */
export function FiltrosCasos({
  iniciales,
  fases,
  estados,
  hayFiltros,
  children,
}: {
  iniciales: ValoresFiltro
  fases: string[]
  estados: { valor: string; etiqueta: string }[]
  hayFiltros: boolean
  /** Resultados renderizados en el servidor para los filtros confirmados. */
  children: ReactNode
}) {
  const router = useRouter()
  const ruta = usePathname()
  const [pendiente, iniciarTransicion] = useTransition()
  const [valores, setValores] = useState(iniciales)
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Si los filtros confirmados cambian desde fuera (chip "quitar", Limpiar, atrás), se adoptan.
  // Si es el eco de lo que acabamos de pedir, los valores locales ya coinciden o van por delante.
  const firmaInicial = JSON.stringify(iniciales)
  const [firmaVista, setFirmaVista] = useState(firmaInicial)
  const [firmaPedida, setFirmaPedida] = useState(firmaInicial)
  if (firmaInicial !== firmaVista) {
    setFirmaVista(firmaInicial)
    if (firmaInicial !== firmaPedida) {
      setValores(iniciales)
      setFirmaPedida(firmaInicial)
    }
  }

  useEffect(() => () => {
    if (espera.current) clearTimeout(espera.current)
  }, [])

  function aplicar(v: ValoresFiltro) {
    if (espera.current) clearTimeout(espera.current)
    espera.current = null
    setFirmaPedida(JSON.stringify(v))
    iniciarTransicion(() => router.replace(construirUrl(ruta, v), { scroll: false }))
  }

  function cambiar(cambio: Partial<ValoresFiltro>, { conEspera = false } = {}) {
    const v = { ...valores, ...cambio }
    setValores(v)
    if (!conEspera) return aplicar(v)
    if (espera.current) clearTimeout(espera.current)
    espera.current = setTimeout(() => aplicar(v), ESPERA_TEXTO_MS)
  }

  function alEnviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    aplicar(valores)
  }

  return (
    <>
      <form
        method="get"
        role="search"
        aria-label="Filtrar casos"
        onSubmit={alEnviar}
        className="space-y-4 rounded-tarjeta bg-surface p-4 shadow-tarjeta"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Número de causa" htmlFor="q">
            <Input
              id="q"
              name="q"
              type="search"
              value={valores.q}
              onChange={(e) => cambiar({ q: e.target.value }, { conEspera: true })}
              maxLength={60}
              placeholder="Ej.: 17230-2019"
              autoComplete="off"
              spellCheck={false}
              className="font-mono placeholder:font-sans"
            />
          </Field>
          <Field label="Estado" htmlFor="estado">
            <Select id="estado" name="estado" value={valores.estado} onChange={(e) => cambiar({ estado: e.target.value })}>
              <option value="">Todos</option>
              {estados.map((e) => (
                <option key={e.valor} value={e.valor}>
                  {e.etiqueta}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Fase actual" htmlFor="fase">
            <Select id="fase" name="fase" value={valores.fase} onChange={(e) => cambiar({ fase: e.target.value })}>
              <option value="">Todas</option>
              {fases.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Ciudad" htmlFor="ciudad">
            <Input
              id="ciudad"
              name="ciudad"
              type="search"
              value={valores.ciudad}
              onChange={(e) => cambiar({ ciudad: e.target.value }, { conEspera: true })}
              maxLength={60}
              placeholder="Ej.: Quito"
              autoComplete="off"
            />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Checkbox
            id="pendientes"
            name="pendientes"
            value="1"
            checked={valores.pendientes}
            onChange={(e) => cambiar({ pendientes: e.target.checked })}
            label="Solo con revisión pendiente"
          />
          {valores.orden ? <input type="hidden" name="orden" value={valores.orden} /> : null}
          <div className="flex items-center gap-3 sm:ml-auto">
            <span aria-live="polite" className="text-xs text-muted">
              {pendiente ? 'Actualizando resultados…' : ''}
            </span>
            {/* Sin JavaScript, el formulario se envía con este botón; con JavaScript los filtros se aplican solos. */}
            <noscript>
              <button type="submit" className={clasesBoton({ tamano: 'sm' })}>
                Filtrar
              </button>
            </noscript>
            {hayFiltros ? (
              <ButtonLink href="/casos" variante="secundario" tamano="sm">
                Limpiar filtros
              </ButtonLink>
            ) : null}
          </div>
        </div>
      </form>

      <div aria-busy={pendiente || undefined} className="relative">
        {/* Barra fina indeterminada: hay una consulta en curso. */}
        <div
          aria-hidden="true"
          className={cx(
            'pointer-events-none absolute inset-x-0 -top-3 h-0.5 overflow-hidden rounded-full transition-opacity duration-(--duracion-base)',
            pendiente ? 'opacity-100 delay-150' : 'opacity-0',
          )}
        >
          <div className="h-full w-1/3 rounded-full bg-primary animate-barrido" />
        </div>
        <div
          className={cx(
            'transition-opacity duration-(--duracion-base) ease-salida',
            // Atenuar solo si la espera se nota (>150 ms): las respuestas rápidas no parpadean.
            pendiente && 'opacity-55 delay-150',
          )}
        >
          {children}
        </div>
      </div>
    </>
  )
}
