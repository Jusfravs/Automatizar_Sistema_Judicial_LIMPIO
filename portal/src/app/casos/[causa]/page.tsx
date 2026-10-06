import { notFound } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { formatFecha, formatFechaProcesal } from '@/lib/fechas'
import { cx } from '@/lib/cx'
import type { Tono } from '@/lib/tonos'
import { Alert, Badge, Card, CardBody, CardHeader, EstadoBadge, PageHeader, Pagination } from '@/components/ui'
import {
  ACTUACIONES_POR_PAGINA,
  AUDITORIA_DECISION_ETIQUETAS,
  COLUMNAS_ACTUACIONES,
  COLUMNAS_AUDITORIA,
  COLUMNAS_EXPEDIENTE_DETALLE,
  COLUMNAS_REVISION,
  DECISION_ETIQUETAS,
  leerDecisionIA,
  leerPagina,
  nombreEtapa,
  nombreFase,
  primerValor,
  puedeAceptarIA,
  type ActuacionDetalle,
  type AuditoriaDetalle,
  type DecisionRevision,
  type Etapa,
  type ExpedienteDetalle,
  type Fase,
  type ParEtapaFase,
  type RevisionDetalle,
} from '@/lib/casos'
import DetalleActuacion from './DetalleActuacion'
import RevisionForm from './RevisionForm'

export const metadata = { title: 'Detalle de la causa' }

type Props = {
  params: Promise<{ causa: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

function decodificarCausa(valor: string): string | null {
  try {
    return decodeURIComponent(valor)
  } catch {
    return null
  }
}

const TONO_DECISION: Record<string, Tono> = {
  CORREGIR: 'info',
  INSUFICIENTE: 'atencion',
  CONSERVAR: 'exito',
}

function Dato({ titulo, children, ancho = '' }: { titulo: string; children: React.ReactNode; ancho?: string }) {
  return (
    <div className={cx('min-w-0', ancho)}>
      <dt className="text-sm text-muted">{titulo}</dt>
      <dd className="mt-0.5 break-words text-sm text-fg">{children}</dd>
    </div>
  )
}

export default async function CasoPage({ params, searchParams }: Props) {
  const causa = decodificarCausa((await params).causa)
  if (!causa) notFound()
  const pagina = leerPagina(primerValor((await searchParams).pag))
  const desde = (pagina - 1) * ACTUACIONES_POR_PAGINA

  const supabase = await createClient()
  const [exp, act, aud, etapasRes, fasesRes] = await Promise.all([
    supabase.from('expedientes').select(COLUMNAS_EXPEDIENTE_DETALLE).eq('numero_causa', causa).maybeSingle(),
    supabase
      .from('actuaciones_procesales')
      .select(COLUMNAS_ACTUACIONES, { count: 'exact' })
      .eq('numero_causa', causa)
      .order('fecha', { ascending: false })
      .range(desde, desde + ACTUACIONES_POR_PAGINA - 1),
    supabase
      .from('auditorias_ia')
      .select(COLUMNAS_AUDITORIA)
      .eq('numero_causa', causa)
      .order('id', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase.from('catalogo_etapas').select('eta_id, nombre').order('eta_id'),
    supabase.from('catalogo_fases').select('fas_id, eta_id, nombre').order('fas_id'),
  ])

  const fallo = exp.error ?? aud.error ?? etapasRes.error ?? fasesRes.error
  if (fallo) {
    console.error('No se pudo cargar la causa:', fallo.message)
    return (
      <Alert tono="peligro" rol="alert">
        No se pudo cargar la causa. Intenta de nuevo en unos segundos.
      </Alert>
    )
  }
  if (!exp.data) notFound()

  const expediente = exp.data as ExpedienteDetalle
  const auditoria = aud.data as AuditoriaDetalle | null
  const etapas = (etapasRes.data ?? []) as Etapa[]
  const fases = (fasesRes.data ?? []) as Fase[]

  // Una página de actuaciones fuera de rango no es un error.
  const errorActuaciones = act.error && act.error.code !== 'PGRST103'
  if (errorActuaciones) console.error('No se pudieron cargar las actuaciones:', act.error?.message)
  const actuaciones = (act.error ? [] : act.data ?? []) as ActuacionDetalle[]
  const totalActuaciones = act.count ?? 0
  const totalPaginas = Math.max(1, Math.ceil(totalActuaciones / ACTUACIONES_POR_PAGINA))

  let revision: RevisionDetalle | null = null
  let errorRevision = false
  if (auditoria) {
    const rev = await supabase.from('revisiones_ia').select(COLUMNAS_REVISION).eq('auditoria_id', auditoria.id).maybeSingle()
    if (rev.error) {
      console.error('No se pudo cargar la revisión:', rev.error.message)
      errorRevision = true
    } else {
      revision = rev.data as RevisionDetalle | null
    }
  }

  const ia = leerDecisionIA(auditoria?.decision_json ?? null)
  const evidencias = new Set(ia.evidencias)
  const describirPar = (par: ParEtapaFase | null) =>
    par ? `${nombreEtapa(par.eta_id, etapas)} / ${nombreFase(par.fas_id, fases)}` : '-'
  const urlActuaciones = (p: number) => `/casos/${encodeURIComponent(causa)}?pag=${p}`

  return (
    <div className="space-y-6">
      <PageHeader
        titulo={expediente.numero_causa}
        tituloMono
        descripcion={`Actualizado: ${formatFecha(expediente.actualizado_en)}`}
        migas={[{ etiqueta: 'Casos', href: '/casos' }, { etiqueta: expediente.numero_causa }]}
        acciones={expediente.estado ? <EstadoBadge tipo="caso" estado={expediente.estado} /> : undefined}
      />

      {expediente.mensaje_especial && (
        <Alert tono="atencion" titulo="Mensaje especial">
          {expediente.mensaje_especial}
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <Card>
            <CardHeader titulo="Datos del expediente" />
            <CardBody>
              <dl className="grid gap-4 sm:grid-cols-2">
                <Dato titulo="Ciudad">{expediente.ciudad ?? '—'}</Dato>
                <Dato titulo="Tipo de acción">{expediente.tipo_accion ?? '—'}</Dato>
                <Dato titulo="Inicio del juicio">{formatFechaProcesal(expediente.fecha_inicio_juicio)}</Dato>
                <Dato titulo="Total de actuaciones">{expediente.total_actuaciones ?? totalActuaciones}</Dato>
                <Dato titulo="Actor" ancho="sm:col-span-2">{expediente.actor ?? '—'}</Dato>
                <Dato titulo="Demandado" ancho="sm:col-span-2">{expediente.demandado ?? '—'}</Dato>
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader titulo="Clasificación" />
            <CardBody>
              <div className="grid gap-6 sm:grid-cols-2">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-fg">Último hito</h3>
                  <dl className="space-y-3">
                    <Dato titulo="Etapa">{expediente.ultima_etapa ?? '—'}</Dato>
                    <Dato titulo="Fase">{expediente.ultima_fase ?? '—'}</Dato>
                    <Dato titulo="Fecha de cierre">{formatFechaProcesal(expediente.fecha_fin_ultima_fase)}</Dato>
                  </dl>
                </div>
                <div className="space-y-3 rounded-control bg-surface-2 p-4">
                  <h3 className="text-sm font-semibold text-fg">Estado actual</h3>
                  <dl className="space-y-3">
                    <Dato titulo="Etapa">{expediente.etapa_actual ?? '—'}</Dato>
                    <Dato titulo="Fase">{expediente.fase_actual ?? '—'}</Dato>
                    <Dato titulo="Inicio de la fase">{formatFechaProcesal(expediente.fecha_inicio_fase_actual)}</Dato>
                  </dl>
                </div>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              titulo="Actuaciones"
              descripcion={`${totalActuaciones} ${totalActuaciones === 1 ? 'actuación' : 'actuaciones'}, de la más reciente a la más antigua`}
            />
            <CardBody className="space-y-4">
              {errorActuaciones ? (
                <Alert tono="peligro">No se pudieron cargar las actuaciones.</Alert>
              ) : actuaciones.length === 0 ? (
                <p className="text-sm text-muted">Esta causa no tiene actuaciones en esta página.</p>
              ) : (
                <ol className="space-y-0">
                  {actuaciones.map((a) => {
                    const esEvidencia = evidencias.has(a.actuacion_id)
                    return (
                      <li key={a.actuacion_id} className="relative flex gap-4 pb-5 last:pb-0">
                        <span aria-hidden="true" className="absolute left-[5px] top-3 h-full w-px bg-(--border-subtle)" />
                        <span
                          aria-hidden="true"
                          className={cx(
                            'relative z-10 mt-1.5 size-[11px] shrink-0 rounded-full border-2',
                            esEvidencia ? 'border-info-solid bg-info-solid' : 'border-strong bg-surface',
                          )}
                        />
                        <div
                          className={cx(
                            'min-w-0 flex-1 space-y-1',
                            esEvidencia && 'rounded-control border border-info-border bg-info-soft p-3',
                          )}
                        >
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                            <span className="text-sm font-semibold tabular-nums text-fg">{formatFechaProcesal(a.fecha)}</span>
                            {a.carpeta ? <span className="text-xs text-muted">{a.carpeta}</span> : null}
                            {esEvidencia && <Badge tono="info">Evidencia IA</Badge>}
                          </div>
                          <p className="text-sm font-medium text-fg">{a.titulo}</p>
                          <DetalleActuacion texto={a.detalle} />
                        </div>
                      </li>
                    )
                  })}
                </ol>
              )}
              <Pagination
                pagina={pagina}
                totalPaginas={totalPaginas}
                hrefPagina={urlActuaciones}
                etiqueta="Paginación de actuaciones"
              />
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
          <Card>
            <CardHeader
              titulo="Auditoría de IA"
              acciones={
                auditoria ? (
                  <Badge tono={ia.decision ? TONO_DECISION[ia.decision] : 'neutral'}>
                    {ia.decision ? AUDITORIA_DECISION_ETIQUETAS[ia.decision] : 'Sin decisión'}
                  </Badge>
                ) : undefined
              }
            />
            <CardBody>
              {!auditoria ? (
                <p className="text-sm text-muted">Esta causa aún no tiene auditoría de IA.</p>
              ) : (
                <dl className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <Dato titulo="Confianza">{ia.confianza !== null ? `${Math.round(ia.confianza * 100)} %` : '—'}</Dato>
                    <Dato titulo="Fecha">{formatFecha(auditoria.creado_en)}</Dato>
                  </div>
                  <Dato titulo="Motivo">{ia.motivo ?? '—'}</Dato>
                  <Dato titulo="Último hito propuesto">{describirPar(ia.ultimo_hito)}</Dato>
                  <Dato titulo="Estado actual propuesto">{describirPar(ia.estado_actual)}</Dato>
                  {ia.evidencias.length > 0 && (
                    <Dato titulo="Evidencias">
                      {ia.evidencias.length} actuación(es) citada(s). Aparecen resaltadas en la línea de actuaciones.
                    </Dato>
                  )}
                  <Dato titulo="Modelo">
                    <span className="break-all text-xs text-muted">{auditoria.modelo}</span>
                  </Dato>
                </dl>
              )}
            </CardBody>
          </Card>

          {auditoria && (errorRevision || revision) && (
            <Card>
              <CardHeader
                titulo="Revisión humana"
                acciones={
                  revision?.estado === 'PENDIENTE' ? (
                    <Badge tono="atencion">Pendiente</Badge>
                  ) : revision?.estado === 'RESUELTA' ? (
                    <Badge tono="exito">Resuelta</Badge>
                  ) : undefined
                }
              />
              <CardBody>
                {errorRevision && <Alert tono="atencion">No se pudo cargar la revisión. Recarga la página.</Alert>}
                {revision?.estado === 'PENDIENTE' && (
                  <RevisionForm auditoriaId={auditoria.id} permiteAceptarIA={puedeAceptarIA(ia)} etapas={etapas} fases={fases} />
                )}
                {revision?.estado === 'RESUELTA' && (
                  <dl className="space-y-3">
                    <Dato titulo="Decisión">
                      {DECISION_ETIQUETAS[revision.decision_humana as DecisionRevision] ?? revision.decision_humana ?? '—'}
                    </Dato>
                    <Dato titulo="Revisado">{formatFecha(revision.revisado_en)}</Dato>
                    {revision.eta_id_manual !== null && (
                      <Dato titulo="Clasificación manual">
                        {nombreEtapa(revision.eta_id_manual, etapas)} / {nombreFase(revision.fas_id_manual, fases)}
                      </Dato>
                    )}
                    {revision.observacion && <Dato titulo="Observación">{revision.observacion}</Dato>}
                  </dl>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
