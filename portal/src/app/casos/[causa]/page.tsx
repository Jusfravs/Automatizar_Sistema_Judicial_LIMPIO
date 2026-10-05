import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import CasoDetalle from './CasoDetalle'
import {
  COLUMNAS_EXPEDIENTE_DETALLE,
  COLUMNAS_ACTUACIONES,
  COLUMNAS_AUDITORIA,
  COLUMNAS_REVISION,
  type ExpedienteDetalle,
  type ActuacionDetalle,
  type AuditoriaDetalle,
  type RevisionDetalle,
  type CatalogoEtapas,
  type CatalogoFases,
} from '@/lib/casos'
import { traducirErrorInterno } from '@/lib/lotes'

const ACTUACIONES_POR_PAGINA = 100

type SearchParams = {
  pag?: string
  pagAct?: string
}

type Props = {
  params: Promise<{ causa: string }>
  searchParams: Promise<SearchParams>
}

async function getExpediente(causa: string): Promise<{ data: ExpedienteDetalle | null; error: string | null }> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('expedientes')
    .select(COLUMNAS_EXPEDIENTE_DETALLE)
    .eq('numero_causa', causa)
    .maybeSingle()

  if (error) return { data: null, error: traducirErrorInterno(error.message) }
  if (!data) return { data: null, error: null }
  return { data: data as ExpedienteDetalle, error: null }
}

async function getActuaciones(causa: string, page: number): Promise<{ data: ActuacionDetalle[]; count: number; error: string | null }> {
  const supabase = await createClient()
  const from = (page - 1) * ACTUACIONES_POR_PAGINA
  const to = from + ACTUACIONES_POR_PAGINA - 1

  const { data, error, count } = await supabase
    .from('actuaciones_procesales')
    .select(COLUMNAS_ACTUACIONES, { count: 'exact' })
    .eq('numero_causa', causa)
    .order('fecha', { ascending: false })
    .range(from, to)

  if (error) {
    console.error('Error fetching actuaciones:', error)
    return { data: [], count: 0, error: traducirErrorInterno(error.message) }
  }
  return { data: data as ActuacionDetalle[], count: count ?? 0, error: null }
}

async function getAuditoria(causa: string): Promise<{ data: AuditoriaDetalle | null; error: string | null }> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('auditorias_ia')
    .select(COLUMNAS_AUDITORIA)
    .eq('numero_causa', causa)
    .order('id', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error) return { data: null, error: traducirErrorInterno(error.message) }
  if (!data) return { data: null, error: null }
  return { data: data as AuditoriaDetalle, error: null }
}

async function getRevision(auditoriaId: number): Promise<{ data: RevisionDetalle | null; error: string | null }> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('revisiones_ia')
    .select(COLUMNAS_REVISION)
    .eq('auditoria_id', auditoriaId)
    .maybeSingle()

  if (error) return { data: null, error: traducirErrorInterno(error.message) }
  if (!data) return { data: null, error: null }
  return { data: data as RevisionDetalle, error: null }
}

async function getCatalogos(): Promise<{ etapas: CatalogoEtapas; fases: CatalogoFases; error: string | null }> {
  const supabase = await createClient()
  const [{ data: etapas, error: errEtapas }, { data: fases, error: errFases }] = await Promise.all([
    supabase.from('catalogo_etapas').select('eta_id, nombre').order('eta_id'),
    supabase.from('catalogo_fases').select('fas_id, eta_id, nombre').order('fas_id'),
  ])

  if (errEtapas || errFases) {
    console.error('Error fetching catalogos:', errEtapas ?? errFases)
    return { etapas: [], fases: [], error: 'No se pudieron cargar los catálogos' }
  }
  return { etapas: etapas as CatalogoEtapas, fases: fases as CatalogoFases, error: null }
}

export default async function CasoIdPage({ params, searchParams }: Props) {
  const { causa: causaEncoded } = await params
  const causa = decodeURIComponent(causaEncoded)
  const { pagAct = '1' } = await searchParams

  const pageAct = Math.max(1, parseInt(pagAct, 10) || 1)

  const [expedienteResult, auditoriaResult, catalogosResult] = await Promise.all([
    getExpediente(causa),
    getAuditoria(causa),
    getCatalogos(),
  ])

  if (expedienteResult.error || auditoriaResult.error || catalogosResult.error) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          Error al cargar la causa
        </div>
      </div>
    )
  }

  const expediente = expedienteResult.data
  if (!expediente) notFound()

  const auditoria = auditoriaResult.data
  let revision = null

  if (auditoria) {
    const revResult = await getRevision(auditoria.id)
    if (!revResult.error && revResult.data) {
      revision = revResult.data
    }
  }

  const [actuacionesResult] = await Promise.all([
    getActuaciones(causa, pageAct),
  ])

  return (
    <CasoDetalle
      expediente={expediente}
      auditoria={auditoria}
      revision={revision}
      actuaciones={actuacionesResult.data}
      actuacionesCount={actuacionesResult.count}
      actuacionesError={actuacionesResult.error}
      pageAct={pageAct}
      totalPagesAct={Math.ceil((actuacionesResult.count ?? 0) / ACTUACIONES_POR_PAGINA)}
      etapas={catalogosResult.etapas}
      fases={catalogosResult.fases}
      causa={causa}
    />
  )
}