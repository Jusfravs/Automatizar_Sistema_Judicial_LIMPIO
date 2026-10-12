import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import { Alert } from '@/components/ui'
import LoteDetalle from './LoteDetalle'
import { leerEstadoServidor, textoServidor } from '@/lib/servidor'
import {
  COLUMNAS_COLA_ERROR,
  COLUMNAS_ESTADO_EJECUCION,
  COLUMNAS_SOLICITUD,
  ESTADOS_COLA_CON_ERROR,
  type ColaError,
  type EstadoEjecucion,
  type SolicitudDetalle,
} from '@/lib/lotes'

export const metadata = { title: 'Detalle del lote' }

// Fuera del componente: leer la hora actual durante el render no es puro.
function estadoServidor(supabase: Awaited<ReturnType<typeof createClient>>) {
  return leerEstadoServidor(supabase, Date.now())
}

type Props = {
  params: Promise<{ id: string }>
}

export default async function LoteIdPage({ params }: Props) {
  const { id } = await params
  const supabase = await createClient()

  const [{ data, error }, { data: sesion }] = await Promise.all([
    supabase.from('solicitudes_lote').select(`${COLUMNAS_SOLICITUD}, solicitado_por`).eq('id', id).maybeSingle(),
    supabase.auth.getUser(),
  ])

  if (error) {
    console.error('No se pudo cargar el lote:', error.message)
    return (
      <Alert tono="peligro" rol="alert">
        No se pudo cargar el lote. Intenta de nuevo en unos segundos.
      </Alert>
    )
  }
  if (!data) notFound()
  const solicitud = data as SolicitudDetalle & { solicitado_por: string }

  // Cancelar: solo quien creó el lote o un administrador (la RPC lo exige desde la migración 008).
  let puedeGestionar = false
  if (sesion.user) {
    if (solicitud.solicitado_por === sesion.user.id) {
      puedeGestionar = true
    } else {
      const { data: perfil } = await supabase.from('perfiles').select('rol').eq('id', sesion.user.id).maybeSingle()
      puedeGestionar = perfil?.rol === 'admin'
    }
  }

  const [estado, cola, servidor] = await Promise.all([
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
    estadoServidor(supabase),
  ])

  if (estado?.error) console.error('No se pudo cargar el avance:', estado.error.message)
  if (cola?.error) console.error('No se pudieron cargar las causas con error:', cola.error.message)

  return (
    <LoteDetalle
      solicitud={solicitud}
      estadoEjecucion={(estado?.data as EstadoEjecucion | null) ?? null}
      colaErrores={(cola?.data as ColaError[] | null) ?? []}
      avisoServidor={servidor.tipo === 'caido' ? textoServidor(servidor) : null}
      puedeGestionar={puedeGestionar}
    />
  )
}
