export const ESTADOS_ACTIVOS = ['SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO'] as const

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

// Mapa de errores internos a mensajes legibles
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
  'ck_solicitud_archivo_ruta': 'Ruta de archivo inválida',
  'rls policy': 'No tiene permiso para realizar esta operación',
  'duplicate key': 'Ya existe una solicitud con ese ID',
  'foreign key': 'Referencia inválida',
  'not-null violation': 'Falta un campo obligatorio',
  'check constraint': 'Los datos no cumplen las reglas de validación',

  // RPC errors
  'SOLICITUD_NO_EXISTE': 'La solicitud no existe',
  'SOLICITUD_FINALIZADA': 'El lote ya terminó y no se puede cancelar',
  'ROL_NO_AUTORIZADO': 'No tiene permiso para esta acción',
}

export function traducirErrorInterno(message: string): string {
  const lower = message.toLowerCase()
  for (const [clave, texto] of Object.entries(ERRORES_MAP)) {
    if (lower.includes(clave.toLowerCase())) return texto
  }
  return 'No se pudo completar la operación'
}