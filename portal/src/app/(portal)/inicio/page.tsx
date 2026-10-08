import Link from 'next/link'
import type { ReactNode } from 'react'
import { createClient } from '@/lib/supabase/server'
import {
  Alert,
  Badge,
  ButtonLink,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  EstadoBadge,
  PageHeader,
  ProgressBar,
} from '@/components/ui'
import { calcularAvance, COLUMNAS_ESTADO_EJECUCION, ESTADOS_ACTIVOS, type EstadoEjecucion } from '@/lib/lotes'
import { formatFecha } from '@/lib/fechas'
import { leerEstadoServidor, textoServidor, tonoServidor } from '@/lib/servidor'
import { FOCO } from '@/components/ui/estilos'
import RefrescoInicio from './RefrescoInicio'

export const metadata = { title: 'Inicio' }

const SIETE_DIAS_MS = 7 * 24 * 60 * 60 * 1000

type Conteo = { count: number | null; error: { message: string } | null }

/** null si la consulta falló: se muestra "—" en vez de un cero engañoso. */
function leerConteo(nombre: string, { count, error }: Conteo): number | null {
  if (error) {
    console.error(`No se pudo contar ${nombre}:`, error.message)
    return null
  }
  return count ?? 0
}

function Indicador({
  etiqueta,
  valor,
  href,
  enlace,
  senal,
}: {
  etiqueta: string
  valor: number | null
  href: string
  enlace: string
  senal?: ReactNode
}) {
  return (
    <Card>
      <CardBody className="flex h-full flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-muted">{etiqueta}</span>
          {senal}
        </div>
        {valor === null ? (
          <span className="text-3xl font-semibold tabular-nums text-fg" aria-label="No disponible">
            —
          </span>
        ) : (
          <span className="text-3xl font-semibold tabular-nums text-fg">{valor}</span>
        )}
        <Link href={href} className={`mt-auto rounded-control text-sm font-medium text-primary underline-offset-2 hover:underline ${FOCO}`}>
          {enlace}
        </Link>
      </CardBody>
    </Card>
  )
}

type Supabase = Awaited<ReturnType<typeof createClient>>

type LoteEnCurso = { id: string; archivo_nombre: string; estado: string; ejecucion_id: string | null; creado_en: string }

async function lotesEnCurso(supabase: Supabase) {
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('id, archivo_nombre, estado, ejecucion_id, creado_en')
    .in('estado', ESTADOS_ACTIVOS)
    .order('creado_en', { ascending: false })
    .limit(5)

  if (error) {
    console.error('No se pudieron cargar los lotes en curso:', error.message)
    return { lotes: [] as LoteEnCurso[], avance: new Map<string, EstadoEjecucion>(), error: true }
  }

  const lotes: LoteEnCurso[] = data ?? []
  const ids = lotes.flatMap((l) => (l.ejecucion_id ? [l.ejecucion_id] : []))
  const avance = new Map<string, EstadoEjecucion>()
  if (ids.length > 0) {
    const res = await supabase.from('v_estado_ejecuciones').select(`id, ${COLUMNAS_ESTADO_EJECUCION}`).in('id', ids)
    if (res.error) console.error('No se pudo cargar el avance de los lotes:', res.error.message)
    for (const fila of res.data ?? []) if (fila.id) avance.set(fila.id, fila)
  }
  return { lotes, avance, error: false }
}

function estadoServidor(supabase: Supabase) {
  return leerEstadoServidor(supabase, Date.now())
}

function contarIndicadores(supabase: Supabase) {
  const hace7Dias = new Date(Date.now() - SIETE_DIAS_MS).toISOString()
  return Promise.all([
    supabase.from('solicitudes_lote').select('id', { count: 'exact', head: true }).in('estado', ESTADOS_ACTIVOS),
    supabase
      .from('solicitudes_lote')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'COMPLETADA')
      .gte('finalizado_en', hace7Dias),
    supabase.from('revisiones_ia').select('id', { count: 'exact', head: true }).eq('estado', 'PENDIENTE'),
    supabase.from('expedientes').select('numero_causa', { count: 'exact', head: true }).eq('estado', 'ERROR_FINAL'),
  ])
}

export default async function InicioPage() {
  const supabase = await createClient()
  const [[activos, completados, pendientes, errorFinal], enCurso, servidor] = await Promise.all([
    contarIndicadores(supabase),
    lotesEnCurso(supabase),
    estadoServidor(supabase),
  ])
  const consultadoEn = new Date().toISOString()

  const nPendientes = leerConteo('las revisiones pendientes', pendientes)
  const nuevoLote = <ButtonLink href="/lotes/nuevo">Nuevo lote</ButtonLink>

  return (
    <div className="space-y-6">
      <PageHeader titulo="Inicio" descripcion="Resumen de lotes y revisiones" acciones={nuevoLote} />

      <RefrescoInicio consultadoEn={consultadoEn} />

      {servidor.tipo === 'caido' ? (
        <Alert tono="peligro" rol="alert" titulo="El servidor de procesamiento no responde">
          Los lotes nuevos quedarán en &ldquo;Solicitada&rdquo; hasta que el servicio vuelva a estar activo
          {servidor.host ? ` en ${servidor.host}` : ''}. {textoServidor(servidor)}.
        </Alert>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted">
          Servidor de procesamiento:
          <Badge tono={tonoServidor(servidor)} punto>
            {textoServidor(servidor)}
          </Badge>
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Indicador
          etiqueta="Lotes activos"
          valor={leerConteo('los lotes activos', activos)}
          href="/lotes"
          enlace="Ver lotes"
        />
        <Indicador
          etiqueta="Completados en 7 días"
          valor={leerConteo('los lotes completados', completados)}
          href="/lotes"
          enlace="Ver lotes"
        />
        <Indicador
          etiqueta="Revisiones pendientes"
          valor={nPendientes}
          href="/casos?pendientes=1"
          enlace="Revisar"
          senal={nPendientes ? <Badge tono="atencion">Requiere atención</Badge> : null}
        />
        <Indicador
          etiqueta="Causas con error final"
          valor={leerConteo('las causas con error final', errorFinal)}
          href="/casos?estado=ERROR_FINAL"
          enlace="Ver causas"
        />
      </div>

      <Card>
        <CardHeader
          titulo="Lotes en curso"
          acciones={
            <ButtonLink href="/lotes" variante="fantasma" tamano="sm">
              Ver todos
            </ButtonLink>
          }
        />
        <CardBody>
          {enCurso.error ? (
            <Alert tono="peligro">No se pudieron cargar los lotes en curso.</Alert>
          ) : enCurso.lotes.length === 0 ? (
            <EmptyState
              titulo="No hay lotes en curso"
              descripcion="Cuando crees un lote, verás aquí su avance."
              accion={nuevoLote}
            />
          ) : (
            <ul className="divide-y divide-subtle">
              {enCurso.lotes.map((lote) => {
                const estado = lote.ejecucion_id ? enCurso.avance.get(lote.ejecucion_id) : undefined
                const valor = calcularAvance(estado ?? null)
                return (
                  <li key={lote.id} className="space-y-2 py-4 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <Link
                        href={`/lotes/${lote.id}`}
                        className={`min-w-0 truncate rounded-control font-medium text-fg underline-offset-2 hover:text-primary hover:underline ${FOCO}`}
                      >
                        {lote.archivo_nombre}
                      </Link>
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-muted">{formatFecha(lote.creado_en)}</span>
                        <EstadoBadge tipo="lote" estado={lote.estado} />
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <ProgressBar valor={valor} etiqueta={`Avance de ${lote.archivo_nombre}`} />
                      <span className="w-20 shrink-0 text-right text-sm tabular-nums text-muted">
                        {estado ? `${valor} %` : 'En espera'}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
