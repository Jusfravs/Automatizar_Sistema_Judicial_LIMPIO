export function formatFecha(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return '-'
    return d.toLocaleString('es-ES', {
      timeZone: 'America/Guayaquil',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '-'
  }
}

/**
 * Formatea fechas procesales que pueden venir en dos formatos:
 * - ISO: '2021-06-05T00:39:21.000+00:00' -> formatea solo fecha dd/mm/aaaa
 * - 'dd/mm/aaaa': '18/12/2025' -> devuelve tal cual
 * - Otros: devuelve el texto original o '-' si está vacío
 */
export function formatFechaProcesal(valor: string | null | undefined): string {
  if (!valor) return '-'
  const v = valor.trim()
  if (!v) return '-'

  // Detectar formato dd/mm/aaaa (con separador / o -)
  const ddmmaaaa = /^\d{2}[\/\-]\d{2}[\/\-]\d{4}$/
  if (ddmmaaaa.test(v)) return v

  // Intentar parsear como ISO
  try {
    const d = new Date(v)
    if (isNaN(d.getTime())) return v
    return d.toLocaleDateString('es-ES', {
      timeZone: 'America/Guayaquil',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return v
  }
}