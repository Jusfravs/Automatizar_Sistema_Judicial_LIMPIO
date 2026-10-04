import { createClient } from '@/lib/supabase/server'
import ProtectedLayout from '@/app/protected-layout'
import { notFound } from 'next/navigation'
import LoteDetalle from './LoteDetalle'
import type { Database } from '@/lib/database.types'

type SolicitudRow = Database['public']['Tables']['solicitudes_lote']['Row']
type EstadoEjecucionRow = Database['public']['Views']['v_estado_ejecuciones']['Row']
type ColaTrabajoRow = Database['public']['Tables']['cola_trabajo']['Row']

type Props = {
  params: Promise<{ id: string }>
}

async function getSolicitud(id: string): Promise<SolicitudRow | null> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('*')
    .eq('id', id)
    .single()

  if (error || !data) return null
  return data
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
    .single()

  if (error || !data) return null
  return data
}

async function getColaTrabajoErrores(ejecucionId: string | null): Promise<Pick<ColaTrabajoRow, 'numero_causa' | 'estado' | 'intentos' | 'ultimo_error'>[]> {
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
  const solicitud = await getSolicitud(id)

  if (!solicitud) notFound()

  const estadoEjecucion = await getEstadoEjecucion(solicitud.perfil)
  const colaErrores = await getColaTrabajoErrores(solicitud.ejecucion_id)

  const estadosActivos = ['SOLICITADA', 'TOMADA', 'PREPARANDO', 'EN_CURSO']

  return (
    <ProtectedLayout>
      <LoteDetalle
        solicitud={solicitud}
        estadoEjecucion={estadoEjecucion}
        colaErrores={colaErrores}
        estadosActivos={estadosActivos}
      />
    </ProtectedLayout>
  )
}