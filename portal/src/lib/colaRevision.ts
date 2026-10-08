import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '@/lib/database.types'

// PostgREST devuelve como máximo 1.000 filas por consulta: la cola se lee por páginas.
const FILAS_POR_PAGINA = 1000
// Tope de seguridad: 50.000 revisiones pendientes es muy superior a cualquier campaña real.
const PAGINAS_MAXIMAS = 50

/** Lugar de una causa en la cola de revisiones pendientes. */
export type ColaRevision = { posicion: number | null; total: number; siguiente: string | null }

/**
 * Causas con revisión pendiente, sin repetir y en orden de llegada (id de la revisión),
 * leyendo TODA la cola por páginas (revisión de Codex: antes se cortaba en 1.000 filas).
 * null si la consulta falla.
 */
export async function leerCausasPendientes(supabase: SupabaseClient<Database>): Promise<string[] | null> {
  const causas: string[] = []
  const vistas = new Set<string>()
  for (let pagina = 0; pagina < PAGINAS_MAXIMAS; pagina++) {
    const desde = pagina * FILAS_POR_PAGINA
    const { data, error } = await supabase
      .from('revisiones_ia')
      .select('numero_causa')
      .eq('estado', 'PENDIENTE')
      .order('id')
      .range(desde, desde + FILAS_POR_PAGINA - 1)
    if (error) {
      console.error('No se pudo leer la cola de revisiones:', error.message)
      return null
    }
    for (const { numero_causa } of data ?? []) {
      if (!vistas.has(numero_causa)) {
        vistas.add(numero_causa)
        causas.push(numero_causa)
      }
    }
    if (!data || data.length < FILAS_POR_PAGINA) break
  }
  return causas
}

/** Posición de `causa` y la siguiente pendiente (circular, sin volver a la misma causa). */
export function ubicarEnCola(causas: string[], causa: string): ColaRevision {
  const indice = causas.indexOf(causa)
  const resto = indice >= 0 ? [...causas.slice(indice + 1), ...causas.slice(0, indice)] : causas.filter((c) => c !== causa)
  return { posicion: indice >= 0 ? indice + 1 : null, total: causas.length, siguiente: resto[0] ?? null }
}
