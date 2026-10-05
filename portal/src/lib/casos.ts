import type { Database } from '@/lib/database.types'

// Tipos base
type ExpedienteRow = Database['public']['Tables']['expedientes']['Row']
type ActuacionRow = Database['public']['Tables']['actuaciones_procesales']['Row']
type AuditoriaRow = Database['public']['Tables']['auditorias_ia']['Row']
type RevisionRow = Database['public']['Tables']['revisiones_ia']['Row']
type EtapaRow = Database['public']['Tables']['catalogo_etapas']['Row']
type FaseRow = Database['public']['Tables']['catalogo_fases']['Row']

// Tipos Pick para lo que se muestra en cada pantalla
export type ExpedienteLista = Pick<ExpedienteRow,
  'numero_causa' | 'ciudad' | 'estado' | 'etapa_actual' | 'fase_actual' |
  'fecha_inicio_fase_actual' | 'actualizado_en'>

export type ExpedienteDetalle = Pick<ExpedienteRow,
  'numero_causa' | 'ciudad' | 'estado' | 'ultima_etapa' | 'ultima_fase' |
  'fecha_fin_ultima_fase' | 'etapa_actual' | 'fase_actual' | 'fecha_inicio_fase_actual' |
  'mensaje_especial' | 'actor' | 'demandado' | 'tipo_accion' | 'fecha_inicio_juicio' |
  'total_actuaciones' | 'actualizado_en' | 'eta_id_etapa_actual' | 'fas_id_fase_actual' |
  'eta_id_ultima_etapa' | 'fas_id_ultima_fase'>

export type ActuacionDetalle = Pick<ActuacionRow,
  'actuacion_id' | 'carpeta' | 'fecha' | 'titulo' | 'detalle'>

export type AuditoriaDetalle = Pick<AuditoriaRow,
  'id' | 'modelo' | 'estado' | 'decision_json' | 'creado_en'>

export type RevisionDetalle = Pick<RevisionRow,
  'estado' | 'decision_humana' | 'eta_id_manual' | 'fas_id_manual' | 'observacion' | 'revisado_en'>

export type CatalogoEtapas = EtapaRow[]
export type CatalogoFases = FaseRow[]

// Columnas para queries
export const COLUMNAS_EXPEDIENTE_LISTA = 'numero_causa, ciudad, estado, etapa_actual, fase_actual, fecha_inicio_fase_actual, actualizado_en'
export const COLUMNAS_EXPEDIENTE_DETALLE = 'numero_causa, ciudad, estado, ultima_etapa, ultima_fase, fecha_fin_ultima_fase, etapa_actual, fase_actual, fecha_inicio_fase_actual, mensaje_especial, actor, demandado, tipo_accion, fecha_inicio_juicio, total_actuaciones, actualizado_en, eta_id_etapa_actual, fas_id_fase_actual, eta_id_ultima_etapa, fas_id_ultima_fase'
export const COLUMNAS_ACTUACIONES = 'actuacion_id, carpeta, fecha, titulo, detalle'
export const COLUMNAS_AUDITORIA = 'id, modelo, estado, decision_json, creado_en'
export const COLUMNAS_REVISION = 'estado, decision_humana, eta_id_manual, fas_id_manual, observacion, revisado_en'

// Estados y etiquetas
export const ESTADOS_CASO = ['PROCESADO', 'REVISION', 'ERROR', 'ERROR_FINAL', 'EXCLUIDO_NO_CORRESPONDE'] as const
export const DECISIONES_REVISION = ['ACEPTAR_SISTEMA', 'ACEPTAR_IA', 'CORREGIR_MANUALMENTE', 'POSPONER'] as const

export const ESTADO_ETIQUETAS: Record<string, string> = {
  PROCESADO: 'Procesado',
  REVISION: 'En revisión',
  ERROR: 'Error',
  ERROR_FINAL: 'Error final',
  EXCLUIDO_NO_CORRESPONDE: 'No corresponde',
}

export const DECISION_ETIQUETAS: Record<string, string> = {
  ACEPTAR_SISTEMA: 'Aceptar sistema',
  ACEPTAR_IA: 'Aceptar IA',
  CORREGIR_MANUALMENTE: 'Corregir manualmente',
  POSPONER: 'Posponer',
}

export const AUDITORIA_DECISION_ETIQUETAS: Record<string, string> = {
  CONSERVAR: 'Conservar',
  CORREGIR: 'Corregir',
  INSUFICIENTE: 'Insuficiente',
}

// Errores específicos de casos (se añaden a ERRORES_MAP de lotes.ts)
export const ERRORES_CASOS_MAP: Record<string, string> = {
  'REVISION_OBSOLETA': 'La revisión ya no es válida: hay una auditoría más nueva o ya fue resuelta',
  'PROPUESTA_IA_INVALIDA': 'La propuesta de la IA no es válida para ser aceptada',
  'EVIDENCIA_INVALIDA': 'Las evidencias de la IA no son válidas',
  'CORRECCION_MANUAL_INVALIDA': 'Falta la etapa/fase válida o la observación para corregir manualmente',
  'IDS_MANUALES_INESPERADOS': 'No se deben enviar etapa/fase con esta decisión',
  'DECISION_INVALIDA': 'Decisión de revisión no válida',
}

// Funciones utilitarias
export function formatoNumeroCausaParaUrl(numero: string): string {
  return encodeURIComponent(numero)
}

export function formatoNumeroCausaDesdeUrl(encoded: string): string {
  return decodeURIComponent(encoded)
}