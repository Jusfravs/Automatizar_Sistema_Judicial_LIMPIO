import type { Database, Json } from '@/lib/database.types'

type ExpedienteRow = Database['public']['Tables']['expedientes']['Row']
type ActuacionRow = Database['public']['Tables']['actuaciones_procesales']['Row']
type AuditoriaRow = Database['public']['Tables']['auditorias_ia']['Row']
type RevisionRow = Database['public']['Tables']['revisiones_ia']['Row']
type EtapaRow = Database['public']['Tables']['catalogo_etapas']['Row']
type FaseRow = Database['public']['Tables']['catalogo_fases']['Row']

export const CASOS_POR_PAGINA = 50
export const ACTUACIONES_POR_PAGINA = 100

export type ExpedienteLista = Pick<ExpedienteRow,
  'numero_causa' | 'ciudad' | 'estado' | 'etapa_actual' | 'fase_actual' |
  'fecha_inicio_fase_actual' | 'actualizado_en'>

export type ExpedienteDetalle = Pick<ExpedienteRow,
  'numero_causa' | 'ciudad' | 'estado' | 'ultima_etapa' | 'ultima_fase' |
  'fecha_fin_ultima_fase' | 'etapa_actual' | 'fase_actual' | 'fecha_inicio_fase_actual' |
  'mensaje_especial' | 'actor' | 'demandado' | 'tipo_accion' | 'fecha_inicio_juicio' |
  'total_actuaciones' | 'actualizado_en'>

export type ActuacionDetalle = Pick<ActuacionRow, 'actuacion_id' | 'carpeta' | 'fecha' | 'titulo' | 'detalle'>
export type AuditoriaDetalle = Pick<AuditoriaRow, 'id' | 'modelo' | 'estado' | 'decision_json' | 'creado_en'>
export type RevisionDetalle = Pick<RevisionRow,
  'estado' | 'decision_humana' | 'eta_id_manual' | 'fas_id_manual' | 'observacion' | 'revisado_en'>
export type Etapa = Pick<EtapaRow, 'eta_id' | 'nombre'>
export type Fase = Pick<FaseRow, 'fas_id' | 'eta_id' | 'nombre'>

export const COLUMNAS_EXPEDIENTE_LISTA =
  'numero_causa, ciudad, estado, etapa_actual, fase_actual, fecha_inicio_fase_actual, actualizado_en'
export const COLUMNAS_EXPEDIENTE_DETALLE =
  'numero_causa, ciudad, estado, ultima_etapa, ultima_fase, fecha_fin_ultima_fase, etapa_actual, fase_actual, fecha_inicio_fase_actual, mensaje_especial, actor, demandado, tipo_accion, fecha_inicio_juicio, total_actuaciones, actualizado_en'
export const COLUMNAS_ACTUACIONES = 'actuacion_id, carpeta, fecha, titulo, detalle'
export const COLUMNAS_AUDITORIA = 'id, modelo, estado, decision_json, creado_en'
export const COLUMNAS_REVISION = 'estado, decision_humana, eta_id_manual, fas_id_manual, observacion, revisado_en'

export const ESTADOS_CASO: readonly string[] = ['PROCESADO', 'REVISION', 'ERROR', 'ERROR_FINAL', 'EXCLUIDO_NO_CORRESPONDE']
export const DECISIONES_REVISION = ['ACEPTAR_SISTEMA', 'ACEPTAR_IA', 'CORREGIR_MANUALMENTE', 'POSPONER'] as const
export type DecisionRevision = (typeof DECISIONES_REVISION)[number]

export const ESTADO_CASO_ETIQUETAS: Record<string, string> = {
  PROCESADO: 'Procesado',
  REVISION: 'En revisión',
  ERROR: 'Error',
  ERROR_FINAL: 'Error final',
  EXCLUIDO_NO_CORRESPONDE: 'No corresponde',
}

export const DECISION_ETIQUETAS: Record<DecisionRevision, string> = {
  ACEPTAR_SISTEMA: 'Aceptar la clasificación del sistema',
  ACEPTAR_IA: 'Aceptar la propuesta de la IA',
  CORREGIR_MANUALMENTE: 'Corregir manualmente',
  POSPONER: 'Posponer',
}

export const AUDITORIA_DECISION_ETIQUETAS: Record<string, string> = {
  CONSERVAR: 'Conservar',
  CORREGIR: 'Corregir',
  INSUFICIENTE: 'Insuficiente',
}

export type ParEtapaFase = { eta_id: number; fas_id: number }

export type DecisionIA = {
  decision: 'CONSERVAR' | 'CORREGIR' | 'INSUFICIENTE' | null
  ultimo_hito: ParEtapaFase | null
  estado_actual: ParEtapaFase | null
  evidencias: string[]
  confianza: number | null
  motivo: string | null
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}

function esEntero(valor: unknown): valor is number {
  return typeof valor === 'number' && Number.isInteger(valor)
}

function leerPar(valor: unknown): ParEtapaFase | null {
  if (!esObjeto(valor) || !esEntero(valor.eta_id) || !esEntero(valor.fas_id)) return null
  return { eta_id: valor.eta_id, fas_id: valor.fas_id }
}

// decision_json lo produce un modelo externo: se valida campo por campo.
export function leerDecisionIA(json: Json | null): DecisionIA {
  const o: Record<string, unknown> = esObjeto(json) ? json : {}
  const decision = o.decision
  const confianza = o.confianza
  return {
    decision: decision === 'CONSERVAR' || decision === 'CORREGIR' || decision === 'INSUFICIENTE' ? decision : null,
    ultimo_hito: leerPar(o.ultimo_hito),
    estado_actual: leerPar(o.estado_actual),
    evidencias: Array.isArray(o.evidencias)
      ? o.evidencias.filter((e): e is string => typeof e === 'string')
      : [],
    confianza: typeof confianza === 'number' && confianza >= 0 && confianza <= 1 ? confianza : null,
    motivo: typeof o.motivo === 'string' && o.motivo.trim() ? o.motivo : null,
  }
}

// Mismas condiciones que exige la RPC registrar_revision para ACEPTAR_IA.
export function puedeAceptarIA(ia: DecisionIA): boolean {
  return ia.decision === 'CORREGIR' && ia.estado_actual !== null && ia.evidencias.length > 0
}

export function nombreEtapa(etaId: number | null | undefined, etapas: Etapa[]): string {
  if (etaId == null) return '-'
  return etapas.find((e) => e.eta_id === etaId)?.nombre ?? String(etaId)
}

export function nombreFase(fasId: number | null | undefined, fases: Fase[]): string {
  if (fasId == null) return '-'
  return fases.find((f) => f.fas_id === fasId)?.nombre ?? String(fasId)
}

export function escaparIlike(valor: string): string {
  return valor.replace(/[\\%_]/g, (c) => `\\${c}`)
}

export function primerValor(valor: string | string[] | undefined): string {
  return (Array.isArray(valor) ? valor[0] : valor)?.trim() ?? ''
}

export function leerPagina(valor: string): number {
  return /^[1-9]\d{0,5}$/.test(valor) ? Number(valor) : 1
}
