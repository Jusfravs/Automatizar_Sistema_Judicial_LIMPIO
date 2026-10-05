import type { Database } from '@/lib/database.types'

export const ESTADOS_ACTIVOS: readonly string[] = ['SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO']
export const ESTADOS_COLA_CON_ERROR = ['ERROR_FINAL', 'REVISION', 'SIN_RESULTADOS', 'PARCIAL']

export const COLUMNAS_SOLICITUD =
  'id, archivo_nombre, hoja, filtros, modo, parametro, trabajadores, continuar, estado, perfil, ejecucion_id, mensaje, resultado_ruta, cancelar, creado_en, tomado_en, finalizado_en, actualizado_en'
export const COLUMNAS_ESTADO_EJECUCION =
  'estado, total_esperado, pendientes, en_proceso, atendidos, errores_finales, trabajadores_configurados, iniciado_en, finalizado_en'
export const COLUMNAS_COLA_ERROR = 'numero_causa, estado, intentos, ultimo_error'

type SolicitudRow = Database['public']['Tables']['solicitudes_lote']['Row']
type EstadoEjecucionRow = Database['public']['Views']['v_estado_ejecuciones']['Row']
type ColaRow = Database['public']['Tables']['cola_trabajo']['Row']

export type SolicitudDetalle = Pick<SolicitudRow,
  'id' | 'archivo_nombre' | 'hoja' | 'filtros' | 'modo' | 'parametro' | 'trabajadores' | 'continuar' |
  'estado' | 'perfil' | 'ejecucion_id' | 'mensaje' | 'resultado_ruta' | 'cancelar' | 'creado_en' |
  'tomado_en' | 'finalizado_en' | 'actualizado_en'>
export type EstadoEjecucion = Pick<EstadoEjecucionRow,
  'estado' | 'total_esperado' | 'pendientes' | 'en_proceso' | 'atendidos' | 'errores_finales' |
  'trabajadores_configurados' | 'iniciado_en' | 'finalizado_en'>
export type ColaError = Pick<ColaRow, 'numero_causa' | 'estado' | 'intentos' | 'ultimo_error'>

export const ESTADO_COLORES: Record<string, string> = {
  SOLICITADA: 'bg-yellow-100 text-yellow-800',
  TOMADA: 'bg-blue-100 text-blue-800',
  PREPARANDO: 'bg-purple-100 text-purple-800',
  EN_CURSO: 'bg-indigo-100 text-indigo-800',
  COMPLETADA: 'bg-green-100 text-green-800',
  FALLIDA: 'bg-red-100 text-red-800',
  RECHAZADA: 'bg-red-100 text-red-800',
  CANCELADA: 'bg-gray-100 text-gray-800',
}

export const ESTADO_ETIQUETAS: Record<string, string> = {
  SOLICITADA: 'Solicitada',
  TOMADA: 'Tomada',
  PREPARANDO: 'Preparando',
  EN_CURSO: 'En curso',
  COMPLETADA: 'Completada',
  FALLIDA: 'Fallida',
  RECHAZADA: 'Rechazada',
  CANCELADA: 'Cancelada',
}

export const MODO_ETIQUETAS: Record<string, string> = {
  solo: 'Una causa',
  lote: 'Lote de N causas',
  pendientes: 'Todas las pendientes',
}

export const FILTROS_DEFAULTS = {
  sucursal: 'TODAS',
  oficina: '',
  estado_judicial: 'ACTIVO',
} as const

export const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
export const MAX_FILE_SIZE = 20 * 1024 * 1024
export const MAX_ARCHIVO_NOMBRE = 255
export const MAX_HOJA = 120

export const ERRORES_MAP: Record<string, string> = {
  // Storage errors
  'mime type not allowed': 'El archivo debe ser .xlsx',
  'file size limit exceeded': 'El archivo no puede superar 20 MB',
  'bucket not found': 'Error de configuración del almacenamiento',
  'The resource already exists': 'El archivo ya existe',

  // Database errors
  'ck_solicitud_parametro': 'El parámetro no es válido para el modo seleccionado',
  'ck_solicitud_trabajadores': 'Los trabajadores deben ser entre 1 y 4',
  'ck_solicitud_modo': 'Modo no válido',
  'ck_solicitud_archivo': 'Ruta de archivo inválida',
  'row-level security': 'No tiene permiso para realizar esta operación',
  'duplicate key': 'Ya existe una solicitud con ese ID',
  'foreign key': 'Referencia inválida',
  'violates not-null': 'Falta un campo obligatorio',
  'check constraint': 'Los datos no cumplen las reglas de validación',
  'jwt expired': 'Tu sesión expiró. Vuelve a iniciar sesión',

  // RPC errors
  'SOLICITUD_NO_EXISTE': 'La solicitud no existe',
  'SOLICITUD_FINALIZADA': 'El lote ya terminó y no se puede cancelar',
  'ROL_NO_AUTORIZADO': 'No tiene permiso para esta acción',
}

export function calcularAvance(estado: EstadoEjecucion | null): number {
  if (!estado?.total_esperado) return 0
  const hechos = (estado.atendidos ?? 0) + (estado.errores_finales ?? 0)
  return Math.min(100, Math.round((hechos / estado.total_esperado) * 100))
}

export function traducirErrorInterno(message: string | null | undefined): string {
  if (!message) return 'No se pudo completar la operación'
  const lower = message.toLowerCase()
  for (const [clave, texto] of Object.entries(ERRORES_MAP)) {
    if (lower.includes(clave.toLowerCase())) return texto
  }
  return 'No se pudo completar la operación'
}