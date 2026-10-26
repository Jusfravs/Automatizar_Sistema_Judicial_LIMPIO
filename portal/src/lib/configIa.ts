import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '@/lib/database.types'

/** Configuración de IA que publica el servicio con su latido (sin claves). */
export interface ConfigIA {
  modo: string
  jerarquia: string
  sombraEnLote: boolean
  incluirTexto: boolean
  proveedor: string
  modelo: string
}

/**
 * Última configuración de IA publicada por el servicio, o null si aún no la publica (servicio
 * anterior o sin la migración 014). Va aparte de leerEstadoServidor: si la columna no existe,
 * el estado del servidor se sigue mostrando.
 */
export async function leerConfigIa(supabase: SupabaseClient<Database>): Promise<ConfigIA | null> {
  const { data, error } = await supabase
    .from('servicio_latido')
    .select('config_ia')
    .not('config_ia', 'is', null)
    .order('latido_en', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (error) {
    console.warn('No se pudo leer la configuración de IA:', error.message)
    return null
  }
  const c = data?.config_ia
  if (!c || typeof c !== 'object' || Array.isArray(c)) return null
  const texto = (v: unknown) => (typeof v === 'string' ? v : '')
  return {
    modo: texto(c.modo) || 'apagado',
    jerarquia: texto(c.jerarquia) || 'motor',
    sombraEnLote: c.sombra_en_lote === true,
    incluirTexto: c.incluir_texto === true,
    proveedor: texto(c.proveedor),
    modelo: texto(c.modelo),
  }
}

/** Frases para Inicio: qué hace la IA, dicho para quien opera el portal. */
export function describirConfigIa(c: ConfigIA): { titulo: string; detalles: string[] } {
  const apagada = c.modo === 'apagado'
  const titulo = apagada
    ? 'IA apagada: decide el motor'
    : c.jerarquia === 'ia_primero'
      ? 'Decide la IA, con respaldo del motor'
      : c.modo === 'sombra'
        ? 'IA en modo sombra: compara, decide el motor'
        : 'Decide el motor'
  if (apagada) return { titulo, detalles: [] }
  const modelo = c.modelo.split('/').pop() || c.modelo
  return {
    titulo,
    detalles: [
      c.sombraEnLote ? 'también en los lotes' : 'solo en auditorías',
      c.incluirTexto ? 'envía el texto de las actuaciones' : 'sin enviar texto',
      ...(modelo ? [`modelo ${modelo}`] : []),
    ],
  }
}
