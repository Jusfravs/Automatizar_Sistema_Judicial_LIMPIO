import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '@/lib/database.types'
import type { Tono } from '@/lib/tonos'

// El servicio late cada 10 s; tres latidos perdidos ya indican que no está atendiendo.
export const LATIDO_VENCIDO_MS = 45_000

export type EstadoServidor =
  | { tipo: 'activo'; procesando: boolean; hace: number; host: string; latidoEn: string }
  | { tipo: 'caido'; hace: number | null; host: string | null; latidoEn: string | null }
  | { tipo: 'desconocido' }

/** Sirve el cliente del servidor y el del navegador (el pulso de Inicio consulta desde el cliente). */
type Supabase = SupabaseClient<Database>

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
  if (!data) return { tipo: 'caido', hace: null, host: null, latidoEn: null }
  return evaluarLatido(data.latido_en, data.estado === 'PROCESANDO', data.worker_host, ahora)
}

/** Clasifica un latido según su antigüedad; el pulso de Inicio lo reevalúa cada segundo. */
export function evaluarLatido(latidoEn: string, procesando: boolean, host: string, ahora: number): EstadoServidor {
  const hace = Math.max(0, ahora - new Date(latidoEn).getTime())
  if (hace > LATIDO_VENCIDO_MS) return { tipo: 'caido', hace, host, latidoEn }
  return { tipo: 'activo', procesando, hace, host, latidoEn }
}

export function describirHace(ms: number | null): string {
  if (ms === null) return 'sin registro'
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
  if (estado.tipo === 'caido') {
    return estado.hace === null
      ? 'Sin conexión: el servicio aún no ha enviado ninguna señal'
      : `Sin conexión: última señal ${describirHace(estado.hace)}`
  }
  return 'Estado desconocido'
}
