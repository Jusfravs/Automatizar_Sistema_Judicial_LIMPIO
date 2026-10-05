'use client'

import { useState, useId, FormEvent } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { formatFecha, formatFechaProcesal } from '@/lib/fechas'
import {
  COLUMNAS_ACTUACIONES,
  DECISIONES_REVISION,
  DECISION_ETIQUETAS,
  AUDITORIA_DECISION_ETIQUETAS,
  type ActuacionDetalle,
  type AuditoriaDetalle,
  type CatalogoEtapas,
  type CatalogoFases,
} from '@/lib/casos'
import { traducirErrorInterno } from '@/lib/lotes'

const ACTUACIONES_POR_PAGINA = 100

interface CasoDetalleProps {
  expediente: {
    numero_causa: string
    ciudad: string | null
    estado: string | null
    ultima_etapa: string | null
    ultima_fase: string | null
    fecha_fin_ultima_fase: string | null
    etapa_actual: string | null
    fase_actual: string | null
    fecha_inicio_fase_actual: string | null
    mensaje_especial: string | null
    actor: string | null
    demandado: string | null
    tipo_accion: string | null
    fecha_inicio_juicio: string | null
    total_actuaciones: number | null
    actualizado_en: string | null
    eta_id_etapa_actual: number | null
    fas_id_fase_actual: number | null
    eta_id_ultima_etapa: number | null
    fas_id_ultima_fase: number | null
  }
  auditoria: AuditoriaDetalle | null
  revision: {
    estado: string
    decision_humana: string | null
    eta_id_manual: number | null
    fas_id_manual: number | null
    observacion: string | null
    revisado_en: string | null
  } | null
  actuaciones: ActuacionDetalle[]
  actuacionesCount: number
  actuacionesError: string | null
  pageAct: number
  totalPagesAct: number
  etapas: CatalogoEtapas
  fases: CatalogoFases
  causa: string
}

type DecisionJson = {
  decision?: string
  ultimo_hito?: { eta_id: number; fas_id: number }
  estado_actual?: { eta_id: number; fas_id: number }
  evidencias?: string[]
  confianza?: number
  motivo?: string
  requiere_revision_humana?: boolean
} | null

function getNombreEtapa(etaId: number | null | undefined, etapas: CatalogoEtapas): string {
  if (!etaId) return '-'
  const etapa = etapas.find((e) => e.eta_id === etaId)
  return etapa?.nombre ?? String(etaId)
}

function getNombreFase(fasId: number | null | undefined, fases: CatalogoFases): string {
  if (!fasId) return '-'
  const fase = fases.find((f) => f.fas_id === fasId)
  return fase?.nombre ?? String(fasId)
}

function getFasesPorEtapa(etaId: number | null, fases: CatalogoFases) {
  if (!etaId) return []
  return fases.filter((f) => f.eta_id === etaId)
}

export default function CasoDetalle({
  expediente,
  auditoria,
  revision,
  actuaciones,
  actuacionesCount,
  actuacionesError,
  pageAct,
  totalPagesAct,
  etapas,
  fases,
  causa,
}: CasoDetalleProps) {
  const supabase = createClient()
  const errorId = useId()

  const [actuacionesData, setActuacionesData] = useState<ActuacionDetalle[]>(actuaciones)
  const [actuacionesPage, setActuacionesPage] = useState(pageAct)
  const [actuacionesTotalPages, setActuacionesTotalPages] = useState(totalPagesAct)
  const [actuacionesErrorState, setActuacionesErrorState] = useState<string | null>(actuacionesError)

  const [revisando, setRevisando] = useState(false)
  const [revisionError, setRevisionError] = useState('')
  const [revisionSuccess, setRevisionSuccess] = useState(false)
  const [revisionDecision, setRevisionDecision] = useState<string>('')
  const [revisionEtaId, setRevisionEtaId] = useState<string>('')
  const [revisionFasId, setRevisionFasId] = useState<string>('')
  const [revisionObservacion, setRevisionObservacion] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const decisionJson = (auditoria?.decision_json as DecisionJson) ?? null
  const evidencias = decisionJson?.evidencias ?? []
  const tieneEvidencias = evidencias.length > 0
  const propuestaCorregir = decisionJson?.decision === 'CORREGIR'

  const revisionPendiente = revision?.estado === 'PENDIENTE'
  const revisionResuelta = revision?.estado === 'RESUELTA'

  const handleActuacionesPageChange = async (newPage: number) => {
    if (newPage < 1 || newPage > actuacionesTotalPages) return
    const supabase = createClient()
    const from = (newPage - 1) * ACTUACIONES_POR_PAGINA
    const to = from + ACTUACIONES_POR_PAGINA - 1

    const { data, error, count } = await supabase
      .from('actuaciones_procesales')
      .select(COLUMNAS_ACTUACIONES, { count: 'exact' })
      .eq('numero_causa', causa)
      .order('fecha', { ascending: false })
      .range(from, to)

    if (error) {
      console.error('Error fetching actuaciones:', error)
      setActuacionesErrorState(traducirErrorInterno(error.message))
      return
    }
    setActuacionesData(data as ActuacionDetalle[])
    setActuacionesPage(newPage)
    setActuacionesTotalPages(Math.ceil((count ?? 0) / ACTUACIONES_POR_PAGINA))
    setActuacionesErrorState(null)
  }

  function validateRevision(): boolean {
    const errors: Record<string, string> = {}

    if (!revisionDecision) {
      errors.decision = 'Debes seleccionar una decisión'
    } else if (!DECISIONES_REVISION.includes(revisionDecision as typeof DECISIONES_REVISION[number])) {
      errors.decision = 'Decisión no válida'
    }

    if (revisionDecision === 'CORREGIR_MANUALMENTE') {
      if (!revisionEtaId) errors.etaId = 'Debes seleccionar una etapa'
      else if (!etapas.some((e) => e.eta_id === parseInt(revisionEtaId, 10))) errors.etaId = 'Etapa no válida'

      if (!revisionFasId) errors.fasId = 'Debes seleccionar una fase'
      else if (!fases.some((f) => f.fas_id === parseInt(revisionFasId, 10))) errors.fasId = 'Fase no válida'
      else {
        const fas = fases.find((f) => f.fas_id === parseInt(revisionFasId, 10))
        if (fas && fas.eta_id !== parseInt(revisionEtaId, 10)) {
          errors.fasId = 'La fase no pertenece a la etapa seleccionada'
        }
      }

      if (!revisionObservacion.trim()) {
        errors.observacion = 'La observación es obligatoria al corregir manualmente'
      } else if (revisionObservacion.length > 1000) {
        errors.observacion = 'La observación no puede superar 1000 caracteres'
      }
    }

    if (revisionDecision === 'ACEPTAR_IA' && !propuestaCorregir) {
      errors.decision = 'Solo se puede ACEPTAR_IA cuando la IA propuso CORREGIR con evidencias'
    }

    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      const firstKey = Object.keys(errors)[0]
      const el = document.getElementById(firstKey)
      el?.focus()
      return false
    }
    return true
  }

  async function handleRevision(e: FormEvent) {
    e.preventDefault()
    setRevisionError('')
    setRevisionSuccess(false)

    if (!validateRevision()) return
    setRevisando(true)

    const pEtaId = revisionDecision === 'CORREGIR_MANUALMENTE' ? parseInt(revisionEtaId, 10) : null
    const pFasId = revisionDecision === 'CORREGIR_MANUALMENTE' ? parseInt(revisionFasId, 10) : null
    const pObservacion = revisionDecision === 'CORREGIR_MANUALMENTE' ? revisionObservacion.trim() : undefined

    const { error } = await supabase.rpc('registrar_revision', {
      p_auditoria_id: auditoria!.id,
      p_decision: revisionDecision,
      p_eta_id: pEtaId ?? undefined,
      p_fas_id: pFasId ?? undefined,
      p_observacion: pObservacion,
    })

    setRevisando(false)

    if (error) {
      console.error('Error en revisión:', error.message)
      setRevisionError(traducirErrorInterno(error.message))
      return
    }

    setRevisionSuccess(true)
    setRevisionDecision('')
    setRevisionEtaId('')
    setRevisionFasId('')
    setRevisionObservacion('')
    setFieldErrors({})
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Causa {causa}</h1>
          <p className="text-sm text-gray-500">Actualizado: {formatFecha(expediente.actualizado_en)}</p>
        </div>
        <Link href="/casos" className="text-sm font-medium text-blue-600 hover:text-blue-900">
          ← Volver al listado
        </Link>
      </div>

      {/* 1. Datos del expediente */}
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="exp-heading">
        <h2 id="exp-heading" className="mb-4 text-lg font-medium text-gray-900">Datos del expediente</h2>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-sm text-gray-500">Ciudad</dt>
            <dd className="mt-1 text-sm text-gray-900">{expediente.ciudad ?? '-'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Estado</dt>
            <dd className="mt-1 text-sm text-gray-900">{expediente.estado ?? '-'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Tipo de acción</dt>
            <dd className="mt-1 text-sm text-gray-900">{expediente.tipo_accion ?? '-'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Fecha inicio juicio</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFechaProcesal(expediente.fecha_inicio_juicio)}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Actor</dt>
            <dd className="mt-1 text-sm text-gray-900">{expediente.actor ?? '-'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Demandado</dt>
            <dd className="mt-1 text-sm text-gray-900">{expediente.demandado ?? '-'}</dd>
          </div>
          {expediente.mensaje_especial && (
            <div className="sm:col-span-4">
              <dt className="text-sm text-gray-500">Mensaje especial</dt>
              <dd className="mt-1 rounded bg-amber-50 p-3 text-sm text-amber-900">{expediente.mensaje_especial}</dd>
            </div>
          )}
        </dl>
      </section>

      {/* 2. Clasificación */}
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="clas-heading">
        <h2 id="clas-heading" className="mb-4 text-lg font-medium text-gray-900">Clasificación</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <h3 className="mb-3 text-sm font-medium text-gray-700">Último hito</h3>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-sm">
              <dt className="text-gray-500">Etapa</dt>
              <dd className="text-gray-900">{getNombreEtapa(expediente.eta_id_ultima_etapa, etapas)}</dd>
              <dt className="text-gray-500">Fase</dt>
              <dd className="text-gray-900">{getNombreFase(expediente.fas_id_ultima_fase, fases)}</dd>
              <dt className="text-gray-500">Fecha fin</dt>
              <dd className="text-gray-900">{formatFechaProcesal(expediente.fecha_fin_ultima_fase)}</dd>
            </dl>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-medium text-gray-700">Estado actual</h3>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-sm">
              <dt className="text-gray-500">Etapa</dt>
              <dd className="text-gray-900">{getNombreEtapa(expediente.eta_id_etapa_actual, etapas)}</dd>
              <dt className="text-gray-500">Fase</dt>
              <dd className="text-gray-900">{getNombreFase(expediente.fas_id_fase_actual, fases)}</dd>
              <dt className="text-gray-500">Inicio fase</dt>
              <dd className="text-gray-900">{formatFechaProcesal(expediente.fecha_inicio_fase_actual)}</dd>
            </dl>
          </div>
        </div>
      </section>

      {/* 3. Auditoría IA */}
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="aud-heading">
        <h2 id="aud-heading" className="mb-4 text-lg font-medium text-gray-900">Auditoría IA</h2>

        {!auditoria ? (
          <div className="rounded bg-blue-50 p-4 text-sm text-blue-700">
            Esta causa aún no tiene auditoría de IA.
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-4">
              <div>
                <dt className="text-sm text-gray-500">Modelo</dt>
                <dd className="mt-1 text-sm text-gray-900">{auditoria.modelo}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Estado</dt>
                <dd className="mt-1 text-sm text-gray-900">{auditoria.estado}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Decisión</dt>
                <dd className="mt-1">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${auditoria.estado === 'CORREGIR' ? 'bg-blue-100 text-blue-800' : auditoria.estado === 'INSUFICIENTE' ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                    {AUDITORIA_DECISION_ETIQUETAS[auditoria.estado] ?? auditoria.estado}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Confianza</dt>
                <dd className="mt-1 text-sm text-gray-900">{decisionJson?.confianza ? `${decisionJson.confianza}%` : '-'}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm text-gray-500">Motivo</dt>
                <dd className="mt-1 text-sm text-gray-900">{decisionJson?.motivo ?? '-'}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm text-gray-500">Último hito propuesto</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {decisionJson?.ultimo_hito
                    ? `${getNombreEtapa(decisionJson.ultimo_hito.eta_id, etapas)} / ${getNombreFase(decisionJson.ultimo_hito.fas_id, fases)}`
                    : '-'}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm text-gray-500">Estado actual propuesto</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {decisionJson?.estado_actual
                    ? `${getNombreEtapa(decisionJson.estado_actual.eta_id, etapas)} / ${getNombreFase(decisionJson.estado_actual.fas_id, fases)}`
                    : '-'}
                </dd>
              </div>
              <div className="sm:col-span-4">
                <dt className="text-sm text-gray-500">Creado</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatFecha(auditoria.creado_en)}</dd>
              </div>
            </dl>

            {tieneEvidencias && (
              <div className="mt-4">
                <h3 className="mb-2 text-sm font-medium text-gray-700">Evidencias (actuaciones referenciadas)</h3>
                <p className="mb-2 text-xs text-gray-500">
                  Las filas resaltadas en la tabla de actuaciones corresponden a estas evidencias:
                </p>
                <div className="flex flex-wrap gap-1 text-xs font-mono text-blue-600">
                  {evidencias.map((e, i) => (
                    <span key={i} className="rounded bg-blue-50 px-2 py-0.5">{e}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* 4. Revisión humana */}
      {auditoria && (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="rev-heading">
          <h2 id="rev-heading" className="mb-4 text-lg font-medium text-gray-900">Revisión humana</h2>

          {revisionResuelta && (
            <div className="rounded bg-green-50 p-4 text-sm text-green-700" role="status">
              <p className="font-medium">Revisión resuelta</p>
              <p>Decisión: <strong>{DECISION_ETIQUETAS[revision!.decision_humana ?? ''] ?? revision!.decision_humana}</strong></p>
              {revision!.eta_id_manual && (
                <p>
                  Etapa: <strong>{getNombreEtapa(revision!.eta_id_manual, etapas)}</strong>,{' '}
                  Fase: <strong>{getNombreFase(revision!.fas_id_manual, fases)}</strong>
                </p>
              )}
              {revision!.observacion && <p className="mt-2">Observación: {revision!.observacion}</p>}
              <p className="mt-2">Revisado: {formatFecha(revision!.revisado_en)}</p>
            </div>
          )}

          {revisionPendiente && (
            <form onSubmit={handleRevision} className="space-y-4" noValidate>
              <fieldset>
                <legend className="mb-3 text-sm font-medium text-gray-700">Decisión</legend>
                <div className="flex flex-wrap gap-4" role="radiogroup" aria-label="Decisión de revisión">
                  {DECISIONES_REVISION.map((d) => (
                    <label key={d} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="decision"
                        value={d}
                        checked={revisionDecision === d}
                        onChange={() => {
                          setRevisionDecision(d)
                          setFieldErrors((prev) => ({ ...prev, decision: '' }))
                        }}
                        disabled={revisando || (d === 'ACEPTAR_IA' && !propuestaCorregir)}
                        className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-900">{DECISION_ETIQUETAS[d]}</span>
                      {d === 'ACEPTAR_IA' && !propuestaCorregir && (
                        <span className="text-xs text-gray-500">(no disponible)</span>
                      )}
                    </label>
                  ))}
                </div>
                {fieldErrors.decision && (
                  <p id={`${errorId}-decision`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.decision}</p>
                )}
              </fieldset>

              {revisionDecision === 'CORREGIR_MANUALMENTE' && (
                <>
                  <fieldset>
                    <legend className="mb-3 text-sm font-medium text-gray-700">Corrección manual</legend>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label htmlFor="etaId" className="block text-sm font-medium text-gray-700">Etapa</label>
                        <select
                          id="etaId"
                          value={revisionEtaId}
                          onChange={(e) => {
                            setRevisionEtaId(e.target.value)
                            setRevisionFasId('')
                            setFieldErrors((prev) => ({ ...prev, etaId: '', fasId: '' }))
                          }}
                          disabled={revisando}
                          aria-invalid={!!fieldErrors.etaId}
                          aria-describedby={fieldErrors.etaId ? `${errorId}-etaId` : undefined}
                          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          <option value="">Seleccionar etapa</option>
                          {etapas.map((e) => (
                            <option key={e.eta_id} value={String(e.eta_id)}>
                              {e.eta_id} - {e.nombre}
                            </option>
                          ))}
                        </select>
                        {fieldErrors.etaId && (
                          <p id={`${errorId}-etaId`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.etaId}</p>
                        )}
                      </div>
                      <div>
                        <label htmlFor="fasId" className="block text-sm font-medium text-gray-700">Fase</label>
                        <select
                          id="fasId"
                          value={revisionFasId}
                          onChange={(e) => {
                            setRevisionFasId(e.target.value)
                            setFieldErrors((prev) => ({ ...prev, fasId: '' }))
                          }}
                          disabled={revisando}
                          aria-invalid={!!fieldErrors.fasId}
                          aria-describedby={fieldErrors.fasId ? `${errorId}-fasId` : undefined}
                          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          <option value="">Seleccionar fase</option>
                          {getFasesPorEtapa(revisionEtaId ? parseInt(revisionEtaId, 10) : null, fases).map((f) => (
                            <option key={f.fas_id} value={String(f.fas_id)}>
                              {f.fas_id} - {f.nombre}
                            </option>
                          ))}
                        </select>
                        {fieldErrors.fasId && (
                          <p id={`${errorId}-fasId`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.fasId}</p>
                        )}
                      </div>
                    </div>
                  </fieldset>
                  <fieldset>
                    <legend className="mb-3 text-sm font-medium text-gray-700">Observación (obligatoria, máx 1000 caracteres)</legend>
                    <textarea
                      id="observacion"
                      value={revisionObservacion}
                      onChange={(e) => {
                        setRevisionObservacion(e.target.value)
                        setFieldErrors((prev) => ({ ...prev, observacion: '' }))
                      }}
                      maxLength={1000}
                      rows={4}
                      disabled={revisando}
                      aria-invalid={!!fieldErrors.observacion}
                      aria-describedby={`${errorId}-observacion ${errorId}-observacion-count`}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {fieldErrors.observacion && (
                      <p id={`${errorId}-observacion`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.observacion}</p>
                    )}
                    <p id={`${errorId}-observacion-count`} className="text-xs text-gray-500 text-right">
                      {revisionObservacion.length}/1000
                    </p>
                  </fieldset>
                </>
              )}

              {revisionError && (
                <p className="rounded bg-red-50 p-3 text-sm text-red-700" role="alert">{revisionError}</p>
              )}
              {revisionSuccess && (
                <p className="rounded bg-green-50 p-3 text-sm text-green-700" role="status">
                  Revisión registrada correctamente
                </p>
              )}

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={revisando}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {revisando ? 'Registrando...' : 'Registrar revisión'}
                </button>
                {revisionSuccess && (
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Actualizar vista
                  </button>
                )}
              </div>
            </form>
          )}
        </section>
      )}

      {/* 5. Actuaciones */}
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="act-heading">
        <h2 id="act-heading" className="mb-4 text-lg font-medium text-gray-900">Actuaciones ({actuacionesCount})</h2>

        {actuacionesErrorState && (
          <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700" role="alert">
            {actuacionesErrorState}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Fecha</th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Carpeta</th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Título</th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Detalle</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {actuacionesData.map((a) => (
                <tr key={a.actuacion_id} className={evidencias.includes(a.actuacion_id) ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                  <td className="px-4 py-3 text-sm text-gray-900 font-mono">{formatFecha(a.fecha)}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{a.carpeta}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{a.titulo}</td>
                  <td className="px-4 py-3">
                    <div className="relative">
                      <p className="line-clamp-2 text-sm text-gray-900 pr-16">{a.detalle}</p>
                      {a.detalle.length > 120 && (
                        <button
                          type="button"
                          onClick={() => alert(a.detalle)}
                          className="absolute right-2 bottom-1 text-xs text-blue-600 hover:text-blue-800"
                          aria-expanded="false"
                          aria-controls={`detalle-${a.actuacion_id}`}
                        >
                          Ver más
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPagesAct > 1 && (
          <div className="mt-4 border-t border-gray-200 pt-4 flex items-center justify-between">
            <p className="text-sm text-gray-500">
              Página {actuacionesPage} de {actuacionesTotalPages} — {actuacionesCount} actuaciones
            </p>
            <div className="flex gap-2">
              {actuacionesPage > 1 && (
                <button
                  onClick={() => handleActuacionesPageChange(actuacionesPage - 1)}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Anterior
                </button>
              )}
              {actuacionesPage < actuacionesTotalPages && (
                <button
                  onClick={() => handleActuacionesPageChange(actuacionesPage + 1)}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Siguiente
                </button>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}