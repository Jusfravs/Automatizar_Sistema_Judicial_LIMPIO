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

const DD_MM_AAAA = /^\d{2}\/\d{2}\/\d{4}$/
const SOLO_FECHA_ISO = /^(\d{4})-(\d{2})-(\d{2})$/
const ISO_CON_HORA = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$/

// Las fechas procesales llegan como 'dd/mm/aaaa' o como ISO con zona; cualquier
// otro texto se muestra tal cual en vez de dejar que Date lo interprete.
export function formatFechaProcesal(valor: string | null | undefined): string {
  const v = valor?.trim() ?? ''
  if (!v) return '-'
  if (DD_MM_AAAA.test(v)) return v
  const soloFecha = SOLO_FECHA_ISO.exec(v)
  if (soloFecha) return `${soloFecha[3]}/${soloFecha[2]}/${soloFecha[1]}`
  if (!ISO_CON_HORA.test(v)) return v
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleDateString('es-ES', {
    timeZone: 'America/Guayaquil',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}