import { createClient } from '@/lib/supabase/server'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card, CardHeader, CardBody } from '@/components/ui/Card'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { Badge } from '@/components/ui/Badge'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { EmptyState } from '@/components/ui/EmptyState'
import { calcularAvance, ESTADOS_ACTIVOS, COLUMNAS_ESTADO_EJECUCION } from '@/lib/lotes'
import type { Database } from '@/lib/database.types'

export const metadata = { title: 'Inicio' }

type EstadoEjecucionRow = Database['public']['Views']['v_estado_ejecuciones']['Row']

async function getIndicadores(supabase: Awaited<ReturnType<typeof createClient>>) {
  const [lotesActivos, completados7d, revisionesPendientes, causasErrorFinal] = await Promise.all([
    supabase
      .from('solicitudes_lote')
      .select('id', { count: 'exact', head: true })
      .in('estado', ESTADOS_ACTIVOS),

    supabase
      .from('solicitudes_lote')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'COMPLETADA')
      .gte('finalizado_en', new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString()),

    supabase
      .from('revisiones_ia')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'PENDIENTE'),

    supabase
      .from('expedientes')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'ERROR_FINAL'),
  ])

  return {
    lotesActivos: lotesActivos.count ?? 0,
    lotesActivosError: lotesActivos.error,
    completados7d: completados7d.count ?? 0,
    completados7dError: completados7d.error,
    revisionesPendientes: revisionesPendientes.count ?? 0,
    revisionesPendientesError: revisionesPendientes.error,
    causasErrorFinal: causasErrorFinal.count ?? 0,
    causasErrorFinalError: causasErrorFinal.error,
  }
}

async function getUserPerfil(supabase: Awaited<ReturnType<typeof createClient>>, userId: string): Promise<string | null> {
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('perfil')
    .eq('solicitado_por', userId)
    .order('creado_en', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error || !data) return null
  return data.perfil
}

async function getEstadoEjecucion(supabase: Awaited<ReturnType<typeof createClient>>, perfil: string | null) {
  if (!perfil) return null

  const { data, error } = await supabase
    .from('v_estado_ejecuciones')
    .select(COLUMNAS_ESTADO_EJECUCION)
    .eq('perfil', perfil)
    .order('creado_en', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error) {
    console.error('Error fetching estado ejecucion:', error)
    return null
  }
  return data as EstadoEjecucionRow | null
}

async function getRevisionesPendientesCount(supabase: Awaited<ReturnType<typeof createClient>>) {
  const { count, error } = await supabase
    .from('revisiones_ia')
    .select('id', { count: 'exact', head: true })
    .eq('estado', 'PENDIENTE')

  if (error) {
    console.error('Error fetching revisiones pendientes:', error)
    return 0
  }
  return count ?? 0
}

function Indicador({
  etiqueta,
  valor,
  error,
  enlace,
  enlaceTexto,
  badge,
}: {
  etiqueta: string
  valor: number
  error: Error | null
  enlace: string
  enlaceTexto: string
  badge?: React.ReactNode
}) {
  return (
    <Card>
      <CardBody className="flex flex-col gap-2">
        <div className="flex items-baseline gap-2">
          <span className="text-sm text-muted">{etiqueta}</span>
          {badge && <span aria-hidden="true">{badge}</span>}
        </div>
        <div className="flex items-baseline gap-2">
          {error ? (
            <span className="text-3xl font-semibold tabular-nums text-fg" aria-label="No disponible">
              —
            </span>
          ) : (
            <span className="text-3xl font-semibold tabular-nums text-fg">{valor}</span>
          )}
        </div>
        <Link
          href={enlace}
          className="text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          {enlaceTexto}
        </Link>
      </CardBody>
    </Card>
  )
}

export default async function InicioPage() {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const { data: profile } = await supabase
    .from('perfiles')
    .select('rol, activo')
    .eq('id', user.id)
    .single()

  if (!profile || !profile.activo) {
    redirect('/sin-acceso')
  }

  const [indicadores, userPerfil, revisionesPendientesCount] = await Promise.all([
    getIndicadores(supabase),
    getUserPerfil(supabase, user.id),
    getRevisionesPendientesCount(supabase),
  ])

  const estadoEjecucion = await getEstadoEjecucion(supabase, userPerfil)

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Inicio"
        descripcion="Resumen de lotes y revisiones"
        acciones={
          <ButtonLink href="/lotes/nuevo" variante="primario">
            Nuevo lote
          </ButtonLink>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Indicador
          etiqueta="Lotes activos"
          valor={indicadores.lotesActivos}
          error={indicadores.lotesActivosError}
          enlace="/lotes"
          enlaceTexto="Ver lotes"
        />
        <Indicador
          etiqueta="Completados en 7 días"
          valor={indicadores.completados7d}
          error={indicadores.completados7dError}
          enlace="/lotes"
          enlaceTexto="Ver lotes"
        />
        <Indicador
          etiqueta="Revisiones pendientes"
          valor={indicadores.revisionesPendientes}
          error={indicadores.revisionesPendientesError}
          enlace="/casos?pendientes=1"
          enlaceTexto="Revisar"
          badge={indicadores.revisionesPendientes > 0 && (
            <Badge tono="atencion" punto>Requiere atención</Badge>
          )}
        />
        <Indicador
          etiqueta="Causas con error final"
          valor={indicadores.causasErrorFinal}
          error={indicadores.causasErrorFinalError}
          enlace="/casos?estado=ERROR_FINAL"
          enlaceTexto="Ver causas"
        />
      </div>

      <Card>
        <CardHeader titulo="Avance del lote en curso" nivel={3} />
        <CardBody>
          {estadoEjecucion ? (
            <ProgressBar
              valor={calcularAvance(estadoEjecucion)}
              etiqueta="Avance del lote"
              tono="progreso"
            />
          ) : (
            <EmptyState
              titulo="No hay lotes en curso"
              descripcion="No se encontró un lote en curso para tu perfil."
            />
          )}
        </CardBody>
      </Card>

      {revisionesPendientesCount > 0 && (
        <Card>
          <CardHeader
            titulo="Lotes activos"
            nivel={3}
            acciones={
              <>
                <ButtonLink href="/lotes/nuevo" variante="primario">
                  Nuevo lote
                </ButtonLink>
                <ButtonLink href="/casos?pendientes=1" variante="secundario">
                  Revisar pendientes
                </ButtonLink>
              </>
            }
          />
          <CardBody>
            <p className="text-sm text-muted">
              Tienes revisiones pendientes. Accede a la lista de casos para revisarlas.
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  )
}