'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import type { Database } from '@/lib/database.types'

type Solicitud = Database['public']['Tables']['solicitudes_lote']['Row']
type EstadoEjecucion = Database['public']['Views']['v_estado_ejecuciones']['Row']
type ColaError = Pick<Database['public']['Tables']['cola_trabajo']['Row'], 'numero_causa' | 'estado' | 'intentos' | 'ultimo_error'>

const ESTADO_COLORES: Record<string, string> = {
  SOLICITADA: 'bg-yellow-100 text-yellow-800',
  TOMADA: 'bg-blue-100 text-blue-800',
  PREPARANDO: 'bg-purple-100 text-purple-800',
  EN_CURSO: 'bg-indigo-100 text-indigo-800',
  COMPLETADA: 'bg-green-100 text-green-800',
  FALLIDA: 'bg-red-100 text-red-800',
  RECHAZADA: 'bg-red-100 text-red-800',
  CANCELADA: 'bg-gray-100 text-gray-800',
}

const ESTADO_ETIQUETAS: Record<string, string> = {
  SOLICITADA: 'Solicitada',
  TOMADA: 'Tomada',
  PREPARANDO: 'Preparando',
  EN_CURSO: 'En curso',
  COMPLETADA: 'Completada',
  FALLIDA: 'Fallida',
  RECHAZADA: 'Rechazada',
  CANCELADA: 'Cancelada',
}

const MODO_ETIQUETAS: Record<string, string> = {
  solo: 'Una causa',
  lote: 'Lote de N causas',
  pendientes: 'Todas las pendientes',
}

const CODIGOS_ERROR: Record<string, string> = {
  ROL_NO_AUTORIZADO: 'El rol no puede hacer esa acción',
  DECISION_INVALIDA: 'Decisión desconocida',
  REVISION_OBSOLETA: 'Ya fue revisada, hay una auditoría más nueva o la versión de la auditoría está vencida',
  PROPUESTA_IA_INVALIDA: 'La IA no propuso un cambio válido',
  EVIDENCIA_INVALIDA: 'La evidencia de la IA no corresponde a la causa',
  CORRECCION_MANUAL_INVALIDA: 'Falta el par válido o la observación',
  IDS_MANUALES_INESPERADOS: 'Se enviaron IDs con una decisión que no los usa',
  SOLICITUD_NO_EXISTE: 'La solicitud no existe',
  SOLICITUD_FINALIZADA: 'El lote ya terminó y no se puede cancelar',
}

function formatFecha(fecha: string | null): string {
  if (!fecha) return '-'
  try {
    const d = new Date(fecha)
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
    return fecha
  }
}

function calcularAvance(estado: EstadoEjecucion | null): number {
  if (!estado || !estado.total_esperado || estado.total_esperado === 0) return 0
  const atendidos = estado.atendidos || 0
  const errores = estado.errores_finales || 0
  return Math.round(((atendidos + errores) / estado.total_esperado) * 100)
}

function traducirError(codigo: string | null): string {
  if (!codigo) return ''
  return CODIGOS_ERROR[codigo] || `Error: ${codigo}`
}

interface LoteDetalleProps {
  solicitud: Solicitud
  estadoEjecucion: EstadoEjecucion | null
  colaErrores: ColaError[]
  estadosActivos: string[]
}

export default function LoteDetalle({
  solicitud,
  estadoEjecucion,
  colaErrores,
  estadosActivos,
}: LoteDetalleProps) {
  const [currentSolicitud, setCurrentSolicitud] = useState<Solicitud>(solicitud)
  const [currentEstadoEjecucion, setCurrentEstadoEjecucion] = useState<EstadoEjecucion | null>(estadoEjecucion)
  const [currentColaErrores, setCurrentColaErrores] = useState<ColaError[]>(colaErrores)
  const [confirmarCancelar, setConfirmarCancelar] = useState(false)
  const [cancelando, setCancelando] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [descargando, setDescargando] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [refreshError, setRefreshError] = useState<string | null>(null)

  const supabase = createClient()

  const esActivo = estadosActivos.includes(currentSolicitud.estado)
  const avance = calcularAvance(currentEstadoEjecucion)

  // Refrescar cada 5s mientras el lote esté activo
  useEffect(() => {
    if (!esActivo) return

    let cancelled = false

    async function tick() {
      if (cancelled) return
      const { data: sol, error: solError } = await supabase
        .from('solicitudes_lote')
        .select('*')
        .eq('id', currentSolicitud.id)
        .maybeSingle()

      if (cancelled) return
      if (solError) {
        setRefreshError('No se pudo actualizar')
        return
      }
      if (!sol) return

      setCurrentSolicitud(sol)

      if (sol.perfil) {
        const { data: est, error: estError } = await supabase
          .from('v_estado_ejecuciones')
          .select('*')
          .eq('perfil', sol.perfil)
          .order('creado_en', { ascending: false })
          .limit(1)
          .single()

        if (cancelled) return
        if (estError) {
          setRefreshError('No se pudo actualizar')
          return
        }
        if (est) setCurrentEstadoEjecucion(est)

        if (sol.ejecucion_id) {
          const { data: cola, error: colaError } = await supabase
            .from('cola_trabajo')
            .select('numero_causa, estado, intentos, ultimo_error')
            .eq('ejecucion_id', sol.ejecucion_id)
            .in('estado', ['ERROR_FINAL', 'REVISION', 'SIN_RESULTADOS', 'PARCIAL'])
            .order('actualizado_en', { ascending: false })

          if (cancelled) return
          if (colaError) {
            setRefreshError('No se pudo actualizar')
            return
          }
          if (cola) setCurrentColaErrores(cola as ColaError[])
        }
      }
    }

    const interval = setInterval(() => {
      tick()
    }, 5000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [esActivo, currentSolicitud.id, supabase])

  async function handleCancelar() {
    setCancelando(true)
    setCancelError('')

    const { data, error } = await supabase.rpc('cancelar_solicitud', { p_id: currentSolicitud.id })

    if (error) {
      setCancelError(traducirError(error.message))
      setCancelando(false)
      return
    }

    const nuevoEstado = (data as string) === 'CANCELADA' ? 'CANCELADA' : currentSolicitud.estado
    setCurrentSolicitud((prev) => ({
      ...prev,
      estado: nuevoEstado,
      cancelar: true,
      mensaje: nuevoEstado === 'CANCELADA' ? 'Lote cancelado' : 'Cancelación solicitada',
    }))
    setConfirmarCancelar(false)
    setCancelando(false)
  }

  async function handleDescargar() {
    if (!currentSolicitud.resultado_ruta) return
    setDescargando(true)
    setDownloadError('')

    const { data, error } = await supabase.storage
      .from('lotes')
      .createSignedUrl(currentSolicitud.resultado_ruta, 60)

    if (error) {
      setDownloadError(`Error al generar enlace: ${error.message}`)
      setDescargando(false)
      return
    }

    window.location.href = data.signedUrl
    setDescargando(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Lote {currentSolicitud.id.slice(0, 8)}…</h1>
          <p className="text-sm text-gray-500">{currentSolicitud.archivo_nombre}</p>
        </div>
        <Link
          href="/lotes"
          className="text-sm font-medium text-blue-600 hover:text-blue-900"
        >
          ← Volver a lotes
        </Link>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-sm text-gray-500">Estado</dt>
            <dd className="mt-1">
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${ESTADO_COLORES[currentSolicitud.estado] || 'bg-gray-100 text-gray-800'}`}>
                {ESTADO_ETIQUETAS[currentSolicitud.estado] || currentSolicitud.estado}
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Modo</dt>
            <dd className="mt-1 text-sm text-gray-900">{MODO_ETIQUETAS[currentSolicitud.modo] || currentSolicitud.modo}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Parámetro</dt>
            <dd className="mt-1 text-sm text-gray-900 font-mono">{currentSolicitud.parametro || '-'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Trabajadores</dt>
            <dd className="mt-1 text-sm text-gray-900">{currentSolicitud.trabajadores}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Filtros</dt>
            <dd className="mt-1 text-sm text-gray-900 font-mono">
              {JSON.stringify(currentSolicitud.filtros ?? {}, null, 2)}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Hoja</dt>
            <dd className="mt-1 text-sm text-gray-900">{currentSolicitud.hoja || 'Primera hoja'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Continuar</dt>
            <dd className="mt-1 text-sm text-gray-900">{currentSolicitud.continuar ? 'Sí' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Creado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(currentSolicitud.creado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Tomado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(currentSolicitud.tomado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Finalizado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(currentSolicitud.finalizado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Actualizado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(currentSolicitud.actualizado_en)}</dd>
          </div>
          {currentSolicitud.mensaje && (
            <div className="sm:col-span-4">
              <dt className="text-sm text-gray-500">Mensaje</dt>
              <dd className="mt-1 text-sm text-gray-900 bg-gray-50 p-3 rounded">{currentSolicitud.mensaje}</dd>
            </div>
          )}
        </dl>
      </div>

      {currentEstadoEjecucion && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Avance de la ejecución</h2>
          <div className="space-y-2">
            <div className="flex items-center gap-4">
              <div className="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden" role="progressbar" aria-valuenow={avance} aria-valuemin={0} aria-valuemax={100} aria-label="Avance del lote">
                <div
                  className="h-full bg-blue-600 transition-all duration-500"
                  style={{ width: `${avance}%` }}
                />
              </div>
              <span className="text-sm font-medium text-gray-900 w-16 text-right">
                {avance}%
              </span>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Total esperado</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.total_esperado || 0}</dd>
              <dt className="text-gray-500">Atendidos</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.atendidos || 0}</dd>
              <dt className="text-gray-500">En proceso</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.en_proceso || 0}</dd>
              <dt className="text-gray-500">Pendientes</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.pendientes || 0}</dd>
              <dt className="text-gray-500">Errores finales</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.errores_finales || 0}</dd>
              <dt className="text-gray-500">Estado ejecución</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.estado || '-'}</dd>
              <dt className="text-gray-500">Trabajadores configurados</dt>
              <dd className="text-gray-900">{currentEstadoEjecucion.trabajadores_configurados || '-'}</dd>
              <dt className="text-gray-500">Iniciado</dt>
              <dd className="text-gray-900">{formatFecha(currentEstadoEjecucion.iniciado_en)}</dd>
              <dt className="text-gray-500">Finalizado</dt>
              <dd className="text-gray-900">{formatFecha(currentEstadoEjecucion.finalizado_en)}</dd>
            </dl>
          </div>
        </div>
      )}

      {currentColaErrores.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Causas con error</h2>
          <div className="overflow-x-auto">
            <table>
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Número de causa</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Estado</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Intentos</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Último error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {currentColaErrores.map((c) => (
                  <tr key={c.numero_causa} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900 font-mono">{c.numero_causa}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{c.estado}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{c.intentos}</td>
                    <td className="px-4 py-3 text-sm text-red-600 max-w-md truncate">
                      {c.ultimo_error ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {refreshError && (
        <div className="text-sm text-amber-700 bg-amber-50 p-3 rounded" role="status">
          {refreshError}
        </div>
      )}

      <div className="flex items-center gap-4">
        {esActivo && !currentSolicitud.cancelar && (
          <button
            type="button"
            onClick={() => setConfirmarCancelar(true)}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Cancelar lote
          </button>
        )}

        {currentSolicitud.cancelar && !estadosActivos.includes(currentSolicitud.estado) && (
          <span className="text-sm text-gray-600">Cancelación solicitada</span>
        )}

        {currentSolicitud.resultado_ruta && (
          <button
            type="button"
            onClick={handleDescargar}
            disabled={descargando}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {descargando ? 'Generando enlace...' : 'Descargar resultado'}
          </button>
        )}

        {cancelError && (
          <div className="text-sm text-red-600" role="alert">{cancelError}</div>
        )}
        {downloadError && (
          <div className="text-sm text-red-600" role="alert">{downloadError}</div>
        )}
      </div>

      {confirmarCancelar && (
        <dialog className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" open>
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" role="document" aria-labelledby="cancel-title">
            <h3 id="cancel-title" className="mb-4 text-lg font-semibold text-gray-900">Confirmar cancelación</h3>
            <p className="mb-6 text-sm text-gray-600">
              ¿Estás seguro de querer cancelar este lote? Se enviará la orden al servicio.
              {currentSolicitud.estado === 'EN_CURSO' && ' El lote ya está en curso, se solicitará la detención.'}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirmarCancelar(false)}
                disabled={cancelando}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                No, volver
              </button>
              <button
                type="button"
                onClick={handleCancelar}
                disabled={cancelando}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cancelando ? 'Cancelando...' : 'Sí, cancelar'}
              </button>
            </div>
          </div>
        </dialog>
      )}
    </div>
  )
}