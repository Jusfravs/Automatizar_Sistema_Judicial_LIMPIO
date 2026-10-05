import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import LoteDetalle from './LoteDetalle'
import {
  COLUMNAS_COLA_ERROR,
  COLUMNAS_ESTADO_EJECUCION,
  COLUMNAS_SOLICITUD,
  ESTADOS_COLA_CON_ERROR,
  type ColaError,
  type EstadoEjecucion,
  type SolicitudDetalle,
} from '@/lib/lotes'

type Props = {
  params: Promise<{ id: string }>
}

export default async function LoteIdPage({ params }: Props) {
  const { id } = await params
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select(COLUMNAS_SOLICITUD)
    .eq('id', id)
    .maybeSingle()

  if (error) {
    console.error('No se pudo cargar el lote:', error.message)
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
        No se pudo cargar el lote. Intenta de nuevo en unos segundos.
      </div>
    )
  }
  if (!data) notFound()
  const solicitud = data as SolicitudDetalle

  const [estado, cola] = await Promise.all([
    solicitud.perfil
      ? supabase
          .from('v_estado_ejecuciones')
          .select(COLUMNAS_ESTADO_EJECUCION)
          .eq('perfil', solicitud.perfil)
          .order('creado_en', { ascending: false })
          .limit(1)
          .maybeSingle()
      : null,
    solicitud.ejecucion_id
      ? supabase
          .from('cola_trabajo')
          .select(COLUMNAS_COLA_ERROR)
          .eq('ejecucion_id', solicitud.ejecucion_id)
          .in('estado', ESTADOS_COLA_CON_ERROR)
          .order('actualizado_en', { ascending: false })
          .limit(200)
      : null,
  ])

  if (estado?.error) console.error('No se pudo cargar el avance:', estado.error.message)
  if (cola?.error) console.error('No se pudieron cargar las causas con error:', cola.error.message)

  return (
    <LoteDetalle
      solicitud={solicitud}
      estadoEjecucion={(estado?.data as EstadoEjecucion | null) ?? null}
      colaErrores={(cola?.data as ColaError[] | null) ?? []}
    />
  )
}
