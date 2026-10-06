import type { Database, Json } from '@/lib/database.types'
import type { Tono } from '@/lib/tonos'

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

// Mapeo estado → tono semántico. Lo consume <EstadoBadge tipo="caso">.
export const ESTADO_CASO_TONOS: Record<string, Tono> = {
  PROCESADO: 'exito',
  REVISION: 'atencion',
  ERROR: 'peligro',
  ERROR_FINAL: 'peligro',
  EXCLUIDO_NO_CORRESPONDE: 'neutral',
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

const ENTIDADES: Record<string, string> = {
  nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", ordm: 'º', ordf: 'ª', deg: '°',
  aacute: 'á', eacute: 'é', iacute: 'í', oacute: 'ó', uacute: 'ú', ntilde: 'ñ', uuml: 'ü',
  Aacute: 'Á', Eacute: 'É', Iacute: 'Í', Oacute: 'Ó', Uacute: 'Ú', Ntilde: 'Ñ', Uuml: 'Ü',
  iexcl: '¡', iquest: '¿', laquo: '«', raquo: '»', ndash: '–', mdash: '—', hellip: '…',
}

// Algunas actuaciones de e-SATJE llegan con el HTML del editor del juzgado. Se muestra como
// texto plano (nunca se interpreta como HTML): saltos de párrafo conservados y entidades decodificadas.
export function textoPlano(valor: string | null | undefined): string {
  if (!valor) return ''
  return valor
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|tr|h[1-6])>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&#x([0-9a-f]{1,6});/gi, (m, h: string) => {
      const n = parseInt(h, 16)
      return n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : m
    })
    .replace(/&#(\d{1,7});/g, (m, d: string) => {
      const n = Number(d)
      return n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : m
    })
    .replace(/&([a-zA-Z]+);/g, (m, nombre: string) => ENTIDADES[nombre] ?? m)
    .replace(/[ \t\u00a0]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
