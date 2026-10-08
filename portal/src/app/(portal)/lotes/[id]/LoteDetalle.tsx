'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createClient } from '@/lib/supabase/client'
import { formatFecha } from '@/lib/fechas'
import { Alert } from '@/components/ui/Alert'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { DataTable, type Columna } from '@/components/ui/DataTable'
import { Dialog } from '@/components/ui/Dialog'
import { EstadoBadge } from '@/components/ui/EstadoBadge'
import { LineaTiempo, type Paso } from '@/components/ui/LineaTiempo'
import { PageHeader } from '@/components/ui/PageHeader'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { cx } from '@/lib/cx'
import type { Json } from '@/lib/database.types'
import {
  COLUMNAS_COLA_ERROR,
  COLUMNAS_ESTADO_EJECUCION,
  COLUMNAS_SOLICITUD,
  ESTADOS_ACTIVOS,
  ESTADOS_COLA_CON_ERROR,
  ESTADO_ETIQUETAS,
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
  /** Texto del estado del servidor si está caído; null si responde. */
  avisoServidor: string | null
}

export default function LoteDetalle({ solicitud, estadoEjecucion, colaErrores, avisoServidor }: LoteDetalleProps) {
  const [actual, setActual] = useState<SolicitudDetalle>(solicitud)
  const [estado, setEstado] = useState<EstadoEjecucion | null>(estadoEjecucion)
  const [cola, setCola] = useState<ColaError[]>(colaErrores)
  const [cancelando, setCancelando] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [descargando, setDescargando] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [refreshError, setRefreshError] = useState(false)
  const [actualizando, setActualizando] = useState(false)
  const [ultimaConsulta, setUltimaConsulta] = useState<Date | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const refrescarAhora = useRef<(() => void) | null>(null)

  const supabase = useMemo(() => createClient(), [])
  const esActivo = ESTADOS_ACTIVOS.includes(actual.estado)
  const avance = calcularAvance(estado)

  useEffect(() => {
    if (!esActivo) return
    let cancelled = false
    let temporizador: ReturnType<typeof setTimeout>
    let enCurso = false
    let refrescoPendiente = false

    async function refrescar(): Promise<boolean> {
      const { data: sol, error: solError } = await supabase
        .from('solicitudes_lote')
        .select(COLUMNAS_SOLICITUD)
        .eq('id', actual.id)
        .maybeSingle()
      if (cancelled) return true
      if (solError || !sol) return false
      const nueva = sol as SolicitudDetalle

      let siguienteEstado: EstadoEjecucion | null = null
      let siguienteCola: ColaError[] | null = null

      if (nueva.perfil) {
        const { data: est, error: estError } = await supabase
          .from('v_estado_ejecuciones')
          .select(COLUMNAS_ESTADO_EJECUCION)
          .eq('perfil', nueva.perfil)
          .order('creado_en', { ascending: false })
          .limit(1)
          .maybeSingle()
        if (cancelled) return true
        if (estError) {
          setActual(nueva)
          return false
        }
        if (est) siguienteEstado = est as EstadoEjecucion
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
        if (colaError) {
          if (siguienteEstado) setEstado(siguienteEstado)
          setActual(nueva)
          return false
        }
        siguienteCola = (filas as ColaError[] | null) ?? []
      }
      if (siguienteEstado) setEstado(siguienteEstado)
      if (siguienteCola) setCola(siguienteCola)
      setActual(nueva)
      return true
    }

    async function ciclo() {
      if (cancelled || document.hidden) return
      if (enCurso) {
        refrescoPendiente = true
        return
      }
      clearTimeout(temporizador)
      enCurso = true
      setActualizando(true)
      try {
        const ok = await refrescar()
        if (cancelled) return
        setRefreshError(!ok)
        if (ok) setUltimaConsulta(new Date())
      } catch (error) {
        console.error('No se pudo actualizar el lote:', error)
        if (!cancelled) setRefreshError(true)
      } finally {
        enCurso = false
        if (!cancelled) {
          setActualizando(false)
          if (!document.hidden) {
            if (refrescoPendiente) {
              refrescoPendiente = false
              void ciclo()
            } else {
              temporizador = setTimeout(ciclo, INTERVALO_REFRESCO_MS)
            }
          }
        }
      }
    }

    function alCambiarVisibilidad() {
      if (document.hidden) clearTimeout(temporizador)
      else void ciclo()
    }

    refrescarAhora.current = () => { void ciclo() }
    document.addEventListener('visibilitychange', alCambiarVisibilidad)
    temporizador = setTimeout(ciclo, INTERVALO_REFRESCO_MS)
    return () => {
      cancelled = true
      clearTimeout(temporizador)
      refrescarAhora.current = null
      document.removeEventListener('visibilitychange', alCambiarVisibilidad)
    }
  }, [esActivo, actual.id, supabase])

  function abrirConfirmacion() {
    setCancelError('')
    setConfirmando(true)
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
    setConfirmando(false)
  }

  async function handleDescargar() {
    if (!actual.resultado_ruta) return
    setDescargando(true)
    setDownloadError('')
    if (actual.resultado_ruta.startsWith('b2:')) {
      try {
        const respuesta = await fetch(`/api/lotes/archivo?id=${encodeURIComponent(actual.id)}`)
        if (!respuesta.ok) throw new Error(`B2_DESCARGA_HTTP_${respuesta.status}`)
        const { url } = await respuesta.json() as { url: string }
        if (!url) throw new Error('B2_ENLACE_INVALIDO')
        window.location.href = url
      } catch {
        setDownloadError('No se pudo generar el enlace de descarga. Intenta de nuevo.')
      } finally {
        setDescargando(false)
      }
      return
    }
    const { data, error } = await supabase.storage.from('lotes').createSignedUrl(actual.resultado_ruta, 60)
    setDescargando(false)
    if (error) {
      console.error('No se pudo generar el enlace de descarga:', error.message)
      setDownloadError('No se pudo generar el enlace de descarga. Intenta de nuevo.')
      return
    }
    window.location.href = data.signedUrl
  }

  const puedeCancelar = esActivo && !actual.cancelar
  const fallido = ESTADOS_FALLIDOS.includes(actual.estado)

  const acciones = (
    <>
      {actual.resultado_ruta && (
        <Button onClick={handleDescargar} cargando={descargando}>
          {descargando ? 'Generando enlace…' : 'Descargar resultado'}
        </Button>
      )}
      {puedeCancelar && (
        <Button variante="peligro" onClick={abrirConfirmacion}>
          Cancelar lote
        </Button>
      )}
    </>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        titulo={actual.archivo_nombre}
        descripcion={`Lote ${actual.id.slice(0, 8)} · creado el ${formatFecha(actual.creado_en)}`}
        migas={[{ etiqueta: 'Lotes', href: '/lotes' }, { etiqueta: actual.archivo_nombre }]}
        acciones={actual.resultado_ruta || puedeCancelar ? acciones : undefined}
      />

      {downloadError && (
        <Alert tono="peligro" rol="alert">
          {downloadError}
        </Alert>
      )}
      {esActivo && actual.cancelar && (
        <Alert tono="info" rol="status">
          Cancelación solicitada. El servicio detendrá el lote en breve.
        </Alert>
      )}
      {avisoServidor && esActivo && !actual.tomado_en && (
        <Alert tono="peligro" rol="alert" titulo="Este lote no avanzará por ahora">
          El servidor de procesamiento no responde ({avisoServidor.toLowerCase()}). El lote se tomará solo en cuanto el servicio
          vuelva a estar activo; no hace falta crearlo de nuevo.
        </Alert>
      )}
      {refreshError && (
        <Alert tono="atencion" rol="status">
          No se pudo actualizar el avance. Se reintentará automáticamente.
        </Alert>
      )}
      {esActivo && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <p>
            {ultimaConsulta ? (
              <>Datos verificados a las <time dateTime={ultimaConsulta.toISOString()}>{ultimaConsulta.toLocaleTimeString('es-EC')}</time></>
            ) : (
              'El avance se actualiza automáticamente cada 5 segundos.'
            )}
          </p>
          <Button variante="secundario" tamano="sm" onClick={() => refrescarAhora.current?.()} disabled={actualizando}>
            Actualizar ahora
          </Button>
        </div>
      )}
      {actual.mensaje && (
        <Alert tono={fallido ? 'peligro' : 'info'} titulo="Mensaje del servicio">
          {actual.mensaje}
        </Alert>
      )}

      <Card>
        <CardHeader titulo="Estado" acciones={<EstadoBadge tipo="lote" estado={actual.estado} />} />
        <CardBody>
          <LineaTiempo etiqueta="Estados del lote" pasos={pasosDelLote(actual)} />
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader titulo="Avance de la ejecución" />
            <CardBody>
              {estado ? (
                <div className="space-y-5">
                  <div className="flex items-end gap-4">
                    <span className="text-4xl font-semibold tabular-nums text-fg">{avance} %</span>
                    <ProgressBar className="mb-2 flex-1" valor={avance} etiqueta="Avance del lote" />
                  </div>
                  <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                    <Contador termino="Total" valor={estado.total_esperado} />
                    <Contador termino="Atendidos" valor={estado.atendidos} />
                    <Contador termino="En proceso" valor={estado.en_proceso} />
                    <Contador termino="Pendientes" valor={estado.pendientes} />
                    <Contador termino="Errores finales" valor={estado.errores_finales} peligro />
                  </dl>
                  <p className="text-xs text-muted">
                    Iniciado: {formatFecha(estado.iniciado_en)} · Finalizado: {formatFecha(estado.finalizado_en)}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-muted">
                  {esActivo ? 'El avance aparecerá cuando el servicio empiece a procesar el lote.' : 'Este lote no tiene datos de ejecución.'}
                </p>
              )}
            </CardBody>
          </Card>

          {cola.length > 0 && (
            <section aria-labelledby="titulo-errores" className="space-y-3">
              <h2 id="titulo-errores" className="text-base font-semibold text-fg">
                Causas con error <span className="font-normal tabular-nums text-muted">({cola.length})</span>
              </h2>
              <DataTable
                etiqueta="Causas con error"
                filas={cola}
                claveFila={(c) => c.numero_causa}
                columnas={COLUMNAS_ERRORES}
              />
            </section>
          )}
        </div>

        <Card className="self-start">
          <CardHeader titulo="Configuración" />
          <CardBody>
            <dl className="space-y-3 text-sm">
              <Dato termino="Modo">{MODO_ETIQUETAS[actual.modo] ?? actual.modo}</Dato>
              <Dato termino="Parámetro">
                <span className="font-mono">{actual.parametro || '—'}</span>
              </Dato>
              <Dato termino="Trabajadores">{actual.trabajadores}</Dato>
              <Dato termino="Hoja">{actual.hoja || 'Primera hoja'}</Dato>
              <Dato termino="Omitir procesadas">{actual.continuar ? 'Sí' : 'No'}</Dato>
              <Dato termino="Filtros">
                <span className="flex flex-wrap gap-1.5">
                  {filtrosLegibles(actual.filtros).map((f) => (
                    <Badge key={f}>{f}</Badge>
                  ))}
                </span>
              </Dato>
              <Dato termino="Última actualización">{formatFecha(actual.actualizado_en)}</Dato>
            </dl>
          </CardBody>
        </Card>
      </div>

      <Dialog
        abierto={confirmando}
        alCerrar={() => {
          if (!cancelando) setConfirmando(false)
        }}
        titulo="¿Cancelar este lote?"
        descripcion={
          actual.estado === 'EN_CURSO'
            ? 'Ya está en curso: se pedirá al servicio que lo detenga.'
            : 'El lote no se procesará.'
        }
        acciones={
          <>
            <Button variante="secundario" onClick={() => setConfirmando(false)} disabled={cancelando} autoFocus>
              No, volver
            </Button>
            <Button variante="peligro" onClick={handleCancelar} cargando={cancelando}>
              {cancelando ? 'Cancelando…' : 'Sí, cancelar'}
            </Button>
          </>
        }
      >
        {cancelError ? (
          <Alert tono="peligro" rol="alert">
            {cancelError}
          </Alert>
        ) : null}
      </Dialog>
    </div>
  )
}

const ESTADOS_FALLIDOS: readonly string[] = ['FALLIDA', 'RECHAZADA', 'CANCELADA']
const ORDEN_ESTADOS = ['SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO', 'COMPLETADA'] as const

/** Pasos de la línea de tiempo. Un lote detenido termina en su estado final marcado como fallo. */
function pasosDelLote(s: SolicitudDetalle): Paso[] {
  const fecha = (clave: string) => {
    if (clave === 'SOLICITADA') return formatFecha(s.creado_en)
    if (clave === 'TOMADA' && s.tomado_en) return formatFecha(s.tomado_en)
    if (clave === 'COMPLETADA' && s.finalizado_en) return formatFecha(s.finalizado_en)
    return undefined
  }

  if (ESTADOS_FALLIDOS.includes(s.estado)) {
    const pasos: Paso[] = [{ clave: 'SOLICITADA', etiqueta: ESTADO_ETIQUETAS.SOLICITADA, detalle: fecha('SOLICITADA'), estado: 'hecho' }]
    if (s.tomado_en) pasos.push({ clave: 'TOMADA', etiqueta: ESTADO_ETIQUETAS.TOMADA, detalle: fecha('TOMADA'), estado: 'hecho' })
    pasos.push({
      clave: s.estado,
      etiqueta: ESTADO_ETIQUETAS[s.estado] ?? s.estado,
      detalle: s.finalizado_en ? formatFecha(s.finalizado_en) : undefined,
      estado: 'fallo',
    })
    return pasos
  }

  const actualIdx = ORDEN_ESTADOS.indexOf(s.estado as (typeof ORDEN_ESTADOS)[number])
  return ORDEN_ESTADOS.map((clave, i) => ({
    clave,
    etiqueta: ESTADO_ETIQUETAS[clave],
    detalle: i <= actualIdx ? fecha(clave) : undefined,
    estado: i < actualIdx || (i === actualIdx && clave === 'COMPLETADA') ? 'hecho' : i === actualIdx ? 'actual' : 'pendiente',
  }))
}

const ETIQUETAS_FILTRO: Record<string, string> = {
  sucursal: 'Sucursal',
  oficina: 'Oficina',
  estado_judicial: 'Estado judicial',
}

/** Filtros guardados como JSON → "Sucursal: TODAS"; los vacíos se muestran como "todas". */
function filtrosLegibles(filtros: Json | null): string[] {
  if (!filtros || typeof filtros !== 'object' || Array.isArray(filtros)) return ['Sin filtros']
  return Object.entries(filtros).map(([clave, valor]) => {
    const texto = typeof valor === 'string' || typeof valor === 'number' ? String(valor).trim() : ''
    return `${ETIQUETAS_FILTRO[clave] ?? clave}: ${texto || 'todas'}`
  })
}

const COLUMNAS_ERRORES: Columna<ColaError>[] = [
  {
    clave: 'causa',
    encabezado: 'Número de causa',
    principal: true,
    celda: (c) => <span className="whitespace-nowrap font-mono text-sm">{c.numero_causa}</span>,
  },
  { clave: 'estado', encabezado: 'Estado', celda: (c) => <span className="text-sm">{c.estado}</span> },
  { clave: 'intentos', encabezado: 'Intentos', className: 'tabular-nums', celda: (c) => c.intentos },
  {
    clave: 'error',
    encabezado: 'Último error',
    celda: (c) => (
      <span className="line-clamp-2 max-w-md text-sm text-peligro-fg" title={c.ultimo_error ?? undefined}>
        {c.ultimo_error ?? '—'}
      </span>
    ),
  },
]

function Contador({ termino, valor, peligro = false }: { termino: string; valor: number | null; peligro?: boolean }) {
  const n = valor ?? 0
  return (
    <div>
      <dt className="text-xs text-muted">{termino}</dt>
      <dd className={cx('text-xl font-semibold tabular-nums', peligro && n > 0 ? 'text-peligro-fg' : 'text-fg')}>{n}</dd>
    </div>
  )
}

function Dato({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{termino}</dt>
      <dd className="mt-0.5 break-words font-medium text-fg">{children}</dd>
    </div>
  )
}
