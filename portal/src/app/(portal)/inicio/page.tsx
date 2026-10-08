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
  NumeroAnimado,
  PageHeader,
  ProgressBar,
} from '@/components/ui'
import { calcularAvance, COLUMNAS_ESTADO_EJECUCION, ESTADOS_ACTIVOS, type EstadoEjecucion } from '@/lib/lotes'
import { formatFecha } from '@/lib/fechas'
import { leerEstadoServidor } from '@/lib/servidor'
import { FOCO } from '@/components/ui/estilos'
import { cx } from '@/lib/cx'
import { NAVEGACION } from '@/lib/transiciones'
import type { Tono } from '@/lib/tonos'
import RefrescoInicio from './RefrescoInicio'
import { PulsoServidor } from './PulsoServidor'

export const metadata = { title: 'Inicio' }

const SIETE_DIAS_MS = 7 * 24 * 60 * 60 * 1000
// Un lote recién terminado sigue en "Lotes en curso" este tiempo: se ve llegar al 100 % en vez de desaparecer.
const RECIEN_TERMINADO_MS = 15 * 60 * 1000

type Conteo = { count: number | null; error: { message: string } | null }

/** null si la consulta falló: se muestra "—" en vez de un cero engañoso. */
function leerConteo(nombre: string, { count, error }: Conteo): number | null {
  if (error) {
    console.error(`No se pudo contar ${nombre}:`, error.message)
    return null
  }
  return count ?? 0
}

/** Barra superior de tono para indicadores que piden acción. */
const ACENTO: Partial<Record<Tono, string>> = {
  atencion: 'bg-atencion-solid',
  peligro: 'bg-peligro-solid',
}

/**
 * Indicador clicable entero (enlace estirado sobre la tarjeta). Con `tono` y valor > 0 muestra una
 * barra superior de color: lo que requiere acción se distingue sin leer.
 */
function Indicador({
  etiqueta,
  valor,
  href,
  enlace,
  senal,
  detalle,
  tono,
}: {
  etiqueta: string
  valor: number | null
  href: string
  enlace: string
  senal?: ReactNode
  detalle?: ReactNode
  tono?: Tono
}) {
  const acento = tono && valor ? ACENTO[tono] : undefined
  return (
    <Card className="group relative overflow-hidden transition-shadow duration-(--duracion-base) hover:shadow-elevada">
      {acento ? <span aria-hidden="true" className={cx('absolute inset-x-0 top-0 h-0.75', acento)} /> : null}
      <CardBody className="flex h-full flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-medium text-muted">{etiqueta}</span>
          {senal}
        </div>
        {valor === null ? (
          <span className="text-display font-semibold tabular-nums text-fg">
            <span aria-hidden="true">—</span>
            <span className="sr-only">No disponible</span>
          </span>
        ) : (
          <NumeroAnimado valor={valor} className="text-display font-semibold text-fg" />
        )}
        {detalle ? <p className="text-xs text-muted">{detalle}</p> : null}
        <Link
          href={href}
          transitionTypes={NAVEGACION}
          className={cx(
            'mt-auto inline-flex items-center gap-1 rounded-control text-sm font-medium text-primary',
            // El enlace cubre toda la tarjeta: objetivo grande sin anidar elementos interactivos.
            'after:absolute after:inset-0 after:content-[""]',
            FOCO,
          )}
        >
          {enlace}
          {/* "Ver lotes" se repite: el destino se precisa con la etiqueta de la tarjeta. */}
          <span className="sr-only">: {etiqueta}</span>
          <span aria-hidden="true" className="transition-transform duration-(--duracion-base) ease-salida group-hover:translate-x-0.5">
            →
          </span>
        </Link>
      </CardBody>
    </Card>
  )
}

/** "3 más que la semana anterior" / "igual que la semana anterior". */
function comparacionSemanal(actual: number | null, anterior: number | null): ReactNode {
  if (actual === null || anterior === null) return null
  const diferencia = actual - anterior
  if (diferencia === 0) return 'Igual que la semana anterior'
  const flecha = diferencia > 0 ? '↑' : '↓'
  const n = Math.abs(diferencia)
  return (
    <>
      <span aria-hidden="true">{flecha} </span>
      {n} {diferencia > 0 ? 'más' : 'menos'} que la semana anterior
    </>
  )
}

type Supabase = Awaited<ReturnType<typeof createClient>>

type LoteEnCurso = {
  id: string
  archivo_nombre: string
  estado: string
  ejecucion_id: string | null
  creado_en: string
}

async function lotesEnCurso(supabase: Supabase, ahora: number) {
  const recientes = new Date(ahora - RECIEN_TERMINADO_MS).toISOString()
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('id, archivo_nombre, estado, ejecucion_id, creado_en')
    // Activos + completados recientes. Fallidos, rechazados y cancelados no son "trabajo en curso".
    .or(`estado.in.(${ESTADOS_ACTIVOS.join(',')}),and(estado.eq.COMPLETADA,finalizado_en.gte."${recientes}")`)
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

function contarIndicadores(supabase: Supabase, ahora: number) {
  const hace7Dias = new Date(ahora - SIETE_DIAS_MS).toISOString()
  const hace14Dias = new Date(ahora - 2 * SIETE_DIAS_MS).toISOString()
  return Promise.all([
    supabase.from('solicitudes_lote').select('id', { count: 'exact', head: true }).in('estado', ESTADOS_ACTIVOS),
    supabase
      .from('solicitudes_lote')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'COMPLETADA')
      .gte('finalizado_en', hace7Dias),
    supabase
      .from('solicitudes_lote')
      .select('id', { count: 'exact', head: true })
      .eq('estado', 'COMPLETADA')
      .gte('finalizado_en', hace14Dias)
      .lt('finalizado_en', hace7Dias),
    supabase.from('revisiones_ia').select('id', { count: 'exact', head: true }).eq('estado', 'PENDIENTE'),
    supabase.from('expedientes').select('numero_causa', { count: 'exact', head: true }).eq('estado', 'ERROR_FINAL'),
  ])
}

/** Todas las consultas del resumen con un mismo instante de referencia (fuera del render). */
async function consultarResumen(supabase: Supabase) {
  const ahora = Date.now()
  const [conteos, enCurso, servidor] = await Promise.all([
    contarIndicadores(supabase, ahora),
    lotesEnCurso(supabase, ahora),
    leerEstadoServidor(supabase, ahora),
  ])
  return { conteos, enCurso, servidor, ahora, consultadoEn: new Date(ahora).toISOString() }
}

export default async function InicioPage() {
  const supabase = await createClient()
  const {
    conteos: [activos, completados, completadosAntes, pendientes, errorFinal],
    enCurso,
    servidor,
    ahora,
    consultadoEn,
  } = await consultarResumen(supabase)

  const nPendientes = leerConteo('las revisiones pendientes', pendientes)
  const nCompletados = leerConteo('los lotes completados', completados)
  const nCompletadosAntes = leerConteo('los lotes completados la semana anterior', completadosAntes)
  const nuevoLote = (
    <ButtonLink href="/lotes/nuevo" transitionTypes={NAVEGACION}>
      Nuevo lote
    </ButtonLink>
  )

  return (
    <div className="space-y-6">
      <PageHeader titulo="Inicio" descripcion="Resumen de lotes y revisiones" acciones={nuevoLote} />

      <div className="space-y-3">
        <PulsoServidor inicial={servidor} instanteServidor={ahora} />
        <RefrescoInicio consultadoEn={consultadoEn} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Indicador
          etiqueta="Lotes activos"
          valor={leerConteo('los lotes activos', activos)}
          href="/lotes"
          enlace="Ver lotes"
        />
        <Indicador
          etiqueta="Completados en 7 días"
          valor={nCompletados}
          detalle={comparacionSemanal(nCompletados, nCompletadosAntes)}
          href="/lotes?estado=COMPLETADA"
          enlace="Ver lotes"
        />
        <Indicador
          etiqueta="Revisiones pendientes"
          valor={nPendientes}
          tono="atencion"
          href="/casos?pendientes=1"
          enlace="Revisar"
          senal={nPendientes ? <Badge tono="atencion">Requiere atención</Badge> : null}
        />
        <Indicador
          etiqueta="Causas con error final"
          valor={leerConteo('las causas con error final', errorFinal)}
          tono="peligro"
          href="/casos?estado=ERROR_FINAL"
          enlace="Ver causas"
        />
      </div>

      <Card>
        <CardHeader
          titulo="Lotes en curso"
          acciones={
            <ButtonLink href="/lotes" variante="fantasma" tamano="sm" transitionTypes={NAVEGACION}>
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
                const terminado = lote.estado === 'COMPLETADA'
                const activo = ESTADOS_ACTIVOS.includes(lote.estado)
                const valor = terminado ? 100 : calcularAvance(estado ?? null)
                return (
                  <li key={lote.id} className="space-y-2 py-4 first:pt-0 last:pb-0">
                      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                        <Link
                          href={`/lotes/${lote.id}`}
                          transitionTypes={NAVEGACION}
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
                        <ProgressBar
                          valor={valor}
                          tono={terminado ? 'exito' : activo ? 'progreso' : 'neutral'}
                          etiqueta={`Avance de ${lote.archivo_nombre}`}
                        />
                        <span className="w-20 shrink-0 text-right text-sm tabular-nums text-muted">
                          {estado || terminado ? `${valor} %` : 'En espera'}
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
