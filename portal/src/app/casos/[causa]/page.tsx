import Link from 'next/link'
import { notFound } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { formatFecha, formatFechaProcesal } from '@/lib/fechas'
import {
  ACTUACIONES_POR_PAGINA,
  AUDITORIA_DECISION_ETIQUETAS,
  COLUMNAS_ACTUACIONES,
  COLUMNAS_AUDITORIA,
  COLUMNAS_EXPEDIENTE_DETALLE,
  COLUMNAS_REVISION,
  DECISION_ETIQUETAS,
  ESTADO_CASO_ETIQUETAS,
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

const COLOR_DECISION: Record<string, string> = {
  CORREGIR: 'bg-blue-100 text-blue-800',
  INSUFICIENTE: 'bg-amber-100 text-amber-800',
  CONSERVAR: 'bg-green-100 text-green-800',
}

function Dato({ titulo, children, ancho = '' }: { titulo: string; children: React.ReactNode; ancho?: string }) {
  return (
    <div className={ancho}>
      <dt className="text-sm text-gray-500">{titulo}</dt>
      <dd className="mt-1 text-sm text-gray-900">{children}</dd>
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
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
        No se pudo cargar la causa. Intenta de nuevo en unos segundos.
      </div>
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-2xl font-semibold text-gray-900">{expediente.numero_causa}</h1>
          <p className="text-sm text-gray-500">Actualizado: {formatFecha(expediente.actualizado_en)}</p>
        </div>
        <Link href="/casos" className="text-sm font-medium text-blue-600 hover:text-blue-900">← Volver al listado</Link>
      </div>

      <section aria-labelledby="titulo-expediente" className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 id="titulo-expediente" className="mb-4 text-lg font-medium text-gray-900">Datos del expediente</h2>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Dato titulo="Ciudad">{expediente.ciudad ?? '-'}</Dato>
          <Dato titulo="Estado">{expediente.estado ? (ESTADO_CASO_ETIQUETAS[expediente.estado] ?? expediente.estado) : '-'}</Dato>
          <Dato titulo="Tipo de acción">{expediente.tipo_accion ?? '-'}</Dato>
          <Dato titulo="Inicio del juicio">{formatFechaProcesal(expediente.fecha_inicio_juicio)}</Dato>
          <Dato titulo="Actor" ancho="sm:col-span-2">{expediente.actor ?? '-'}</Dato>
          <Dato titulo="Demandado" ancho="sm:col-span-2">{expediente.demandado ?? '-'}</Dato>
          <Dato titulo="Total de actuaciones">{expediente.total_actuaciones ?? totalActuaciones}</Dato>
          {expediente.mensaje_especial && (
            <Dato titulo="Mensaje especial" ancho="sm:col-span-4">
              <span className="block rounded bg-amber-50 p-3 text-amber-900">{expediente.mensaje_especial}</span>
            </Dato>
          )}
        </dl>
      </section>

      <section aria-labelledby="titulo-clasificacion" className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 id="titulo-clasificacion" className="mb-4 text-lg font-medium text-gray-900">Clasificación</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <h3 className="mb-3 text-sm font-medium text-gray-700">Último hito</h3>
            <dl className="space-y-3">
              <Dato titulo="Etapa">{expediente.ultima_etapa ?? '-'}</Dato>
              <Dato titulo="Fase">{expediente.ultima_fase ?? '-'}</Dato>
              <Dato titulo="Fecha de cierre">{formatFechaProcesal(expediente.fecha_fin_ultima_fase)}</Dato>
            </dl>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-medium text-gray-700">Estado actual</h3>
            <dl className="space-y-3">
              <Dato titulo="Etapa">{expediente.etapa_actual ?? '-'}</Dato>
              <Dato titulo="Fase">{expediente.fase_actual ?? '-'}</Dato>
              <Dato titulo="Inicio de la fase">{formatFechaProcesal(expediente.fecha_inicio_fase_actual)}</Dato>
            </dl>
          </div>
        </div>
      </section>

      <section aria-labelledby="titulo-auditoria" className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 id="titulo-auditoria" className="mb-4 text-lg font-medium text-gray-900">Auditoría de IA</h2>
        {!auditoria ? (
          <p className="rounded bg-gray-50 p-4 text-sm text-gray-600">Esta causa aún no tiene auditoría de IA.</p>
        ) : (
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Dato titulo="Decisión">
              <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ia.decision ? COLOR_DECISION[ia.decision] : 'bg-gray-100 text-gray-800'}`}>
                {ia.decision ? AUDITORIA_DECISION_ETIQUETAS[ia.decision] : 'Sin decisión'}
              </span>
            </Dato>
            <Dato titulo="Confianza">{ia.confianza !== null ? `${Math.round(ia.confianza * 100)} %` : '-'}</Dato>
            <Dato titulo="Modelo">{auditoria.modelo}</Dato>
            <Dato titulo="Fecha">{formatFecha(auditoria.creado_en)}</Dato>
            <Dato titulo="Motivo" ancho="sm:col-span-4">{ia.motivo ?? '-'}</Dato>
            <Dato titulo="Último hito propuesto" ancho="sm:col-span-2">{describirPar(ia.ultimo_hito)}</Dato>
            <Dato titulo="Estado actual propuesto" ancho="sm:col-span-2">{describirPar(ia.estado_actual)}</Dato>
            {ia.evidencias.length > 0 && (
              <Dato titulo="Evidencias" ancho="sm:col-span-4">
                {ia.evidencias.length} actuación(es) citada(s). Aparecen resaltadas en la tabla de actuaciones.
              </Dato>
            )}
          </dl>
        )}
      </section>

      {auditoria && (errorRevision || revision) && (
        <section aria-labelledby="titulo-revision" className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 id="titulo-revision" className="mb-4 text-lg font-medium text-gray-900">Revisión humana</h2>
          {errorRevision && (
            <p className="rounded bg-amber-50 p-3 text-sm text-amber-800">No se pudo cargar la revisión. Recarga la página.</p>
          )}
          {revision?.estado === 'PENDIENTE' && (
            <RevisionForm auditoriaId={auditoria.id} permiteAceptarIA={puedeAceptarIA(ia)} etapas={etapas} fases={fases} />
          )}
          {revision?.estado === 'RESUELTA' && (
            <dl className="grid grid-cols-1 gap-4 rounded bg-green-50 p-4 sm:grid-cols-2">
              <Dato titulo="Decisión">
                {DECISION_ETIQUETAS[revision.decision_humana as DecisionRevision] ?? revision.decision_humana ?? '-'}
              </Dato>
              <Dato titulo="Revisado">{formatFecha(revision.revisado_en)}</Dato>
              {revision.eta_id_manual !== null && (
                <Dato titulo="Clasificación manual" ancho="sm:col-span-2">
                  {nombreEtapa(revision.eta_id_manual, etapas)} / {nombreFase(revision.fas_id_manual, fases)}
                </Dato>
              )}
              {revision.observacion && <Dato titulo="Observación" ancho="sm:col-span-2">{revision.observacion}</Dato>}
            </dl>
          )}
        </section>
      )}

      <section aria-labelledby="titulo-actuaciones" className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 id="titulo-actuaciones" className="mb-4 text-lg font-medium text-gray-900">Actuaciones</h2>
        {errorActuaciones ? (
          <p className="rounded bg-amber-50 p-3 text-sm text-amber-800">No se pudieron cargar las actuaciones.</p>
        ) : actuaciones.length === 0 ? (
          <p className="text-sm text-gray-500">Esta causa no tiene actuaciones en esta página.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50">
                <tr>
                  {['Fecha', 'Carpeta', 'Título', 'Detalle'].map((t) => (
                    <th key={t} scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">{t}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {actuaciones.map((a) => {
                  const esEvidencia = evidencias.has(a.actuacion_id)
                  return (
                    <tr key={a.actuacion_id} className={esEvidencia ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900">
                        {formatFechaProcesal(a.fecha)}
                        {esEvidencia && <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">Evidencia IA</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900">{a.carpeta}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{a.titulo}</td>
                      <td className="px-4 py-3"><DetalleActuacion texto={a.detalle} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <nav aria-label="Paginación de actuaciones" className="mt-4 flex items-center justify-between border-t border-gray-200 pt-4">
          <p className="text-sm text-gray-500">Página {pagina} de {totalPaginas} · {totalActuaciones} actuaciones</p>
          <div className="flex gap-2">
            {pagina > 1 && (
              <Link href={urlActuaciones(pagina - 1)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
                Anterior
              </Link>
            )}
            {pagina < totalPaginas && (
              <Link href={urlActuaciones(pagina + 1)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
                Siguiente
              </Link>
            )}
          </div>
        </nav>
      </section>
    </div>
  )
}
