'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { formatFecha } from '@/lib/fechas'
import {
  COLUMNAS_COLA_ERROR,
  COLUMNAS_ESTADO_EJECUCION,
  COLUMNAS_SOLICITUD,
  ESTADO_COLORES,
  ESTADO_ETIQUETAS,
  ESTADOS_ACTIVOS,
  ESTADOS_COLA_CON_ERROR,
  MODO_ETIQUETAS,
  calcularAvance,
  traducirErrorInterno,
  type ColaError,
  type EstadoEjecucion,
  type SolicitudDetalle,
} from '@/lib/lotes'

const INTERVALO_REFRESCO_MS = 5000

interface LoteDetalleProps {
  solicitud: SolicitudDetalle
  estadoEjecucion: EstadoEjecucion | null
  colaErrores: ColaError[]
}

export default function LoteDetalle({ solicitud, estadoEjecucion, colaErrores }: LoteDetalleProps) {
  const [actual, setActual] = useState<SolicitudDetalle>(solicitud)
  const [estado, setEstado] = useState<EstadoEjecucion | null>(estadoEjecucion)
  const [cola, setCola] = useState<ColaError[]>(colaErrores)
  const [cancelando, setCancelando] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [descargando, setDescargando] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [refreshError, setRefreshError] = useState(false)
  const dialogRef = useRef<HTMLDialogElement>(null)

  const supabase = createClient()
  const esActivo = ESTADOS_ACTIVOS.includes(actual.estado)
  const avance = calcularAvance(estado)

  useEffect(() => {
    if (!esActivo) return
    let cancelled = false
    let temporizador: ReturnType<typeof setTimeout>

    async function refrescar(): Promise<boolean> {
      const { data: sol, error: solError } = await supabase
        .from('solicitudes_lote')
        .select(COLUMNAS_SOLICITUD)
        .eq('id', actual.id)
        .maybeSingle()
      if (cancelled) return true
      if (solError || !sol) return false
      const nueva = sol as SolicitudDetalle
      setActual(nueva)

      if (nueva.perfil) {
        const { data: est, error: estError } = await supabase
          .from('v_estado_ejecuciones')
          .select(COLUMNAS_ESTADO_EJECUCION)
          .eq('perfil', nueva.perfil)
          .order('creado_en', { ascending: false })
          .limit(1)
          .maybeSingle()
        if (cancelled) return true
        if (estError) return false
        if (est) setEstado(est as EstadoEjecucion)
      }

      if (nueva.ejecucion_id) {
        const { data: filas, error: colaError } = await supabase
          .from('cola_trabajo')
          .select(COLUMNAS_COLA_ERROR)
          .eq('ejecucion_id', nueva.ejecucion_id)
          .in('estado', ESTADOS_COLA_CON_ERROR)
          .order('actualizado_en', { ascending: false })
          .limit(200)
        if (cancelled) return true
        if (colaError) return false
        setCola((filas as ColaError[] | null) ?? [])
      }
      return true
    }

    async function ciclo() {
      const ok = await refrescar()
      if (cancelled) return
      setRefreshError(!ok)
      temporizador = setTimeout(ciclo, INTERVALO_REFRESCO_MS)
    }

    temporizador = setTimeout(ciclo, INTERVALO_REFRESCO_MS)
    return () => {
      cancelled = true
      clearTimeout(temporizador)
    }
  }, [esActivo, actual.id, supabase])

  function abrirConfirmacion() {
    setCancelError('')
    dialogRef.current?.showModal()
  }

  async function handleCancelar() {
    setCancelando(true)
    setCancelError('')
    const { data, error } = await supabase.rpc('cancelar_solicitud', { p_id: actual.id })
    setCancelando(false)
    if (error) {
      console.error('No se pudo cancelar el lote:', error.message)
      setCancelError(traducirErrorInterno(error.message))
      return
    }
    setActual((prev) => ({
      ...prev,
      cancelar: true,
      ...(data === 'CANCELADA' ? { estado: 'CANCELADA' } : {}),
    }))
    dialogRef.current?.close()
  }

  async function handleDescargar() {
    if (!actual.resultado_ruta) return
    setDescargando(true)
    setDownloadError('')
    const { data, error } = await supabase.storage.from('lotes').createSignedUrl(actual.resultado_ruta, 60)
    setDescargando(false)
    if (error) {
      console.error('No se pudo generar el enlace de descarga:', error.message)
      setDownloadError('No se pudo generar el enlace de descarga. Intenta de nuevo.')
      return
    }
    window.location.href = data.signedUrl
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Lote {actual.id.slice(0, 8)}…</h1>
          <p className="text-sm text-gray-500">{actual.archivo_nombre}</p>
        </div>
        <Link href="/lotes" className="text-sm font-medium text-blue-600 hover:text-blue-900">
          ← Volver a lotes
        </Link>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-sm text-gray-500">Estado</dt>
            <dd className="mt-1">
              <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTADO_COLORES[actual.estado] ?? 'bg-gray-100 text-gray-800'}`}>
                {ESTADO_ETIQUETAS[actual.estado] ?? actual.estado}
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Modo</dt>
            <dd className="mt-1 text-sm text-gray-900">{MODO_ETIQUETAS[actual.modo] ?? actual.modo}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Parámetro</dt>
            <dd className="mt-1 font-mono text-sm text-gray-900">{actual.parametro || '-'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Trabajadores</dt>
            <dd className="mt-1 text-sm text-gray-900">{actual.trabajadores}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm text-gray-500">Filtros</dt>
            <dd className="mt-1 font-mono text-sm text-gray-900">{JSON.stringify(actual.filtros ?? {})}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Hoja</dt>
            <dd className="mt-1 text-sm text-gray-900">{actual.hoja || 'Primera hoja'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Omitir procesadas</dt>
            <dd className="mt-1 text-sm text-gray-900">{actual.continuar ? 'Sí' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Creado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(actual.creado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Tomado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(actual.tomado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Finalizado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(actual.finalizado_en)}</dd>
          </div>
          <div>
            <dt className="text-sm text-gray-500">Actualizado</dt>
            <dd className="mt-1 text-sm text-gray-900">{formatFecha(actual.actualizado_en)}</dd>
          </div>
          {actual.mensaje && (
            <div className="sm:col-span-4">
              <dt className="text-sm text-gray-500">Mensaje</dt>
              <dd className="mt-1 rounded bg-gray-50 p-3 text-sm text-gray-900">{actual.mensaje}</dd>
            </div>
          )}
        </dl>
      </div>

      {estado && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Avance de la ejecución</h2>
          <div className="space-y-2">
            <div className="flex items-center gap-4">
              <div
                className="h-3 flex-1 overflow-hidden rounded-full bg-gray-200"
                role="progressbar"
                aria-valuenow={avance}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Avance del lote"
              >
                <div className="h-full bg-blue-600 transition-all duration-500" style={{ width: `${avance}%` }} />
              </div>
              <span className="w-16 text-right text-sm font-medium text-gray-900">{avance}%</span>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Total esperado</dt>
              <dd className="text-gray-900">{estado.total_esperado ?? 0}</dd>
              <dt className="text-gray-500">Atendidos</dt>
              <dd className="text-gray-900">{estado.atendidos ?? 0}</dd>
              <dt className="text-gray-500">En proceso</dt>
              <dd className="text-gray-900">{estado.en_proceso ?? 0}</dd>
              <dt className="text-gray-500">Pendientes</dt>
              <dd className="text-gray-900">{estado.pendientes ?? 0}</dd>
              <dt className="text-gray-500">Errores finales</dt>
              <dd className="text-gray-900">{estado.errores_finales ?? 0}</dd>
              <dt className="text-gray-500">Iniciado</dt>
              <dd className="text-gray-900">{formatFecha(estado.iniciado_en)}</dd>
              <dt className="text-gray-500">Finalizado</dt>
              <dd className="text-gray-900">{formatFecha(estado.finalizado_en)}</dd>
            </dl>
          </div>
        </div>
      )}

      {cola.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Causas con error</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Número de causa</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Estado</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Intentos</th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Último error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {cola.map((c) => (
                  <tr key={c.numero_causa} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-sm text-gray-900">{c.numero_causa}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{c.estado}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{c.intentos}</td>
                    <td className="max-w-md truncate px-4 py-3 text-sm text-red-600" title={c.ultimo_error ?? undefined}>
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
        <p className="rounded bg-amber-50 p-3 text-sm text-amber-700" role="status">
          No se pudo actualizar el avance. Se reintentará automáticamente.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-4">
        {esActivo && !actual.cancelar && (
          <button
            type="button"
            onClick={abrirConfirmacion}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Cancelar lote
          </button>
        )}

        {esActivo && actual.cancelar && (
          <span className="text-sm text-gray-600" role="status">
            Cancelación solicitada. El servicio detendrá el lote en breve.
          </span>
        )}

        {actual.resultado_ruta && (
          <button
            type="button"
            onClick={handleDescargar}
            disabled={descargando}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {descargando ? 'Generando enlace...' : 'Descargar resultado'}
          </button>
        )}

        {downloadError && <p className="text-sm text-red-600" role="alert">{downloadError}</p>}
      </div>

      <dialog
        ref={dialogRef}
        aria-labelledby="cancelar-titulo"
        aria-describedby="cancelar-descripcion"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl backdrop:bg-black/50"
      >
        <h2 id="cancelar-titulo" className="mb-4 text-lg font-semibold text-gray-900">Confirmar cancelación</h2>
        <p id="cancelar-descripcion" className="mb-6 text-sm text-gray-600">
          ¿Seguro que quieres cancelar este lote?
          {actual.estado === 'EN_CURSO' && ' Ya está en curso: se pedirá al servicio que lo detenga.'}
        </p>
        {cancelError && <p className="mb-4 text-sm text-red-600" role="alert">{cancelError}</p>}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            autoFocus
            onClick={() => dialogRef.current?.close()}
            disabled={cancelando}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            No, volver
          </button>
          <button
            type="button"
            onClick={handleCancelar}
            disabled={cancelando}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {cancelando ? 'Cancelando...' : 'Sí, cancelar'}
          </button>
        </div>
      </dialog>
    </div>
  )
}
