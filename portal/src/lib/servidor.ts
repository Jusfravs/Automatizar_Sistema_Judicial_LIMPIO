import type { createClient } from '@/lib/supabase/server'
import type { Tono } from '@/lib/tonos'

// El servicio late cada 10 s; tres latidos perdidos ya indican que no está atendiendo.
export const LATIDO_VENCIDO_MS = 45_000

export type EstadoServidor =
  | { tipo: 'activo'; procesando: boolean; hace: number; host: string }
  | { tipo: 'caido'; hace: number | null; host: string | null }
  | { tipo: 'desconocido' }

type Supabase = Awaited<ReturnType<typeof createClient>>

/** Último latido de cualquier servidor; `ahora` se recibe para no leer el reloj durante el render. */
export async function leerEstadoServidor(supabase: Supabase, ahora: number): Promise<EstadoServidor> {
  const { data, error } = await supabase
    .from('servicio_latido')
    .select('worker_host, estado, latido_en')
    .order('latido_en', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (error) {
    console.error('No se pudo leer el estado del servidor:', error.message)
    return { tipo: 'desconocido' }
  }
  if (!data) return { tipo: 'caido', hace: null, host: null }
  const hace = Math.max(0, ahora - new Date(data.latido_en).getTime())
  if (hace > LATIDO_VENCIDO_MS) return { tipo: 'caido', hace, host: data.worker_host }
  return { tipo: 'activo', procesando: data.estado === 'PROCESANDO', hace, host: data.worker_host }
}

export function describirHace(ms: number | null): string {
  if (ms === null) return 'nunca se ha conectado'
  const s = Math.round(ms / 1000)
  if (s < 60) return `hace ${s} s`
  const m = Math.round(s / 60)
  if (m < 60) return `hace ${m} min`
  const h = Math.round(m / 60)
  if (h < 48) return `hace ${h} h`
  return `hace ${Math.round(h / 24)} días`
}

export function tonoServidor(estado: EstadoServidor): Tono {
  if (estado.tipo === 'activo') return estado.procesando ? 'progreso' : 'exito'
  if (estado.tipo === 'caido') return 'peligro'
  return 'neutral'
}

export function textoServidor(estado: EstadoServidor): string {
  if (estado.tipo === 'activo') return estado.procesando ? 'Procesando un lote' : 'Activo, esperando lotes'
  if (estado.tipo === 'caido') return `Sin conexión (último aviso ${describirHace(estado.hace)})`
  return 'Estado desconocido'
}
