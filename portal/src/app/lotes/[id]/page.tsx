import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import LoteDetalle from './LoteDetalle'
import type { Database } from '@/lib/database.types'

type SolicitudRow = Database['public']['Tables']['solicitudes_lote']['Row']
type EstadoEjecucionRow = Database['public']['Views']['v_estado_ejecuciones']['Row']
type ColaTrabajoRow = Pick<Database['public']['Tables']['cola_trabajo']['Row'], 'numero_causa' | 'estado' | 'intentos' | 'ultimo_error'>

type Props = {
  params: Promise<{ id: string }>
}

async function getSolicitud(id: string): Promise<{ data: SolicitudRow | null; error: Error | null }> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('*')
    .eq('id', id)
    .maybeSingle()

  if (error) return { data: null, error }
  if (!data) return { data: null, error: null }
  return { data, error: null }
}

async function getEstadoEjecucion(perfil: string | null): Promise<EstadoEjecucionRow | null> {
  if (!perfil) return null
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('v_estado_ejecuciones')
    .select('*')
    .eq('perfil', perfil)
    .order('creado_en', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error || !data) return null
  return data
}

async function getColaTrabajoErrores(ejecucionId: string | null): Promise<ColaTrabajoRow[]> {
  if (!ejecucionId) return []
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('cola_trabajo')
    .select('numero_causa, estado, intentos, ultimo_error')
    .eq('ejecucion_id', ejecucionId)
    .in('estado', ['ERROR_FINAL', 'REVISION', 'SIN_RESULTADOS', 'PARCIAL'])
    .order('actualizado_en', { ascending: false })

  if (error || !data) return []
  return data
}

export default async function LoteIdPage({ params }: Props) {
  const { id } = await params

  const solicitudResult = await getSolicitud(id)

  if (solicitudResult.error) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          Error al cargar el lote
        </div>
      </div>
    )
  }

  const solicitud = solicitudResult.data

  if (!solicitud) notFound()

  const [estadoEjecucion, colaErrores] = await Promise.all([
    solicitud.perfil ? getEstadoEjecucion(solicitud.perfil) : Promise.resolve(null),
    solicitud.ejecucion_id ? getColaTrabajoErrores(solicitud.ejecucion_id) : Promise.resolve([]),
  ])

  return (
    <LoteDetalle
      solicitud={solicitud}
      estadoEjecucion={estadoEjecucion}
      colaErrores={colaErrores}
      estadosActivos={['SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO']}
    />
  )
}