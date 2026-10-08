import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import {
  Alert,
  ButtonLink,
  DataTable,
  EmptyState,
  EstadoBadge,
  PageHeader,
  ProgressBar,
  type Columna,
} from '@/components/ui'
import type { Database } from '@/lib/database.types'
import { formatFecha } from '@/lib/fechas'
import { primerValor } from '@/lib/casos'
import { cx } from '@/lib/cx'
import { FOCO } from '@/components/ui/estilos'
import {
  calcularAvance,
  COLUMNAS_ESTADO_EJECUCION,
  ESTADO_ETIQUETAS,
  MODO_ETIQUETAS,
  type EstadoEjecucion,
} from '@/lib/lotes'

export const metadata = { title: 'Lotes' }

type SolicitudLote = Pick<
  Database['public']['Tables']['solicitudes_lote']['Row'],
  'id' | 'archivo_nombre' | 'modo' | 'parametro' | 'trabajadores' | 'estado' | 'creado_en' | 'mensaje' | 'ejecucion_id'
>

type Supabase = Awaited<ReturnType<typeof createClient>>

function truncate(str: string | null, max: number): string {
  if (!str) return ''
  return str.length > max ? str.slice(0, max) + '…' : str
}

async function getSolicitudes(supabase: Supabase, estado: string | null) {
  let consulta = supabase
    .from('solicitudes_lote')
    .select('id, archivo_nombre, modo, parametro, trabajadores, estado, creado_en, mensaje, ejecucion_id')
    .order('creado_en', { ascending: false })
    .limit(100)
  if (estado) consulta = consulta.eq('estado', estado)

  const { data, error } = await consulta
  if (error) {
    console.error('Error fetching solicitudes:', error)
    return { solicitudes: [] as SolicitudLote[], error: true }
  }
  return { solicitudes: (data ?? []) as SolicitudLote[], error: false }
}

async function getAvance(supabase: Supabase, solicitudes: SolicitudLote[]) {
  const avance = new Map<string, EstadoEjecucion>()
  const ids = solicitudes.flatMap((s) => (s.ejecucion_id ? [s.ejecucion_id] : []))
  if (ids.length === 0) return avance

  const { data, error } = await supabase
    .from('v_estado_ejecuciones')
    .select(`id, ${COLUMNAS_ESTADO_EJECUCION}`)
    .in('id', ids)
  if (error) console.error('No se pudo cargar el avance de los lotes:', error.message)
  for (const fila of data ?? []) if (fila.id) avance.set(fila.id, fila)
  return avance
}

function FiltroEstado({ href, activo, children }: { href: string; activo: boolean; children: string }) {
  return (
    <Link
      href={href}
      aria-current={activo ? 'page' : undefined}
      className={cx(
        'rounded-full border px-3 py-1 text-sm font-medium transition-colors',
        FOCO,
        activo ? 'border-primary bg-primary text-on-primary' : 'border-subtle bg-surface text-muted hover:text-fg',
      )}
    >
      {children}
    </Link>
  )
}

export default async function LotesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const valor = primerValor((await searchParams).estado)
  const estado = Object.hasOwn(ESTADO_ETIQUETAS, valor) ? valor : null

  const supabase = await createClient()
  const { solicitudes, error } = await getSolicitudes(supabase, estado)
  const avance = error ? new Map<string, EstadoEjecucion>() : await getAvance(supabase, solicitudes)

  const nuevoLote = <ButtonLink href="/lotes/nuevo">Nuevo lote</ButtonLink>

  const columnas: Columna<SolicitudLote>[] = [
    {
      clave: 'archivo',
      encabezado: 'Archivo',
      principal: true,
      celda: (s) => (
        <div className="min-w-0">
          <Link href={`/lotes/${s.id}`} className={cx('rounded-sm font-medium text-fg underline-offset-2 transition-colors hover:text-primary hover:underline', FOCO)}>
            {s.archivo_nombre}
          </Link>
          <p className="text-xs text-muted">
            {MODO_ETIQUETAS[s.modo] ?? s.modo}
            {s.parametro ? ` · ${s.parametro}` : ''}
          </p>
        </div>
      ),
    },
    {
      clave: 'estado',
      encabezado: 'Estado',
      celda: (s) => <EstadoBadge tipo="lote" estado={s.estado} />,
    },
    {
      clave: 'avance',
      encabezado: 'Avance',
      celda: (s) => {
        const ejecucion = s.ejecucion_id ? avance.get(s.ejecucion_id) : undefined
        if (!ejecucion) return <span className="text-sm text-muted">—</span>
        const v = calcularAvance(ejecucion)
        return (
          <div className="flex items-center justify-end gap-2 md:justify-start">
            <ProgressBar className="w-20 shrink md:w-24" valor={v} etiqueta={`Avance de ${s.archivo_nombre}`} />
            {/* Cifra y signo juntos: en tarjetas estrechas "100 %" se partía en dos líneas. */}
            <span className="shrink-0 whitespace-nowrap text-sm tabular-nums text-muted">{v}&nbsp;%</span>
          </div>
        )
      },
    },
    {
      clave: 'trabajadores',
      encabezado: 'Trabajadores',
      ocultarEnMovil: true,
      className: 'tabular-nums',
      celda: (s) => s.trabajadores,
    },
    {
      clave: 'creado',
      encabezado: 'Creado',
      celda: (s) => <span className="text-sm text-muted">{formatFecha(s.creado_en)}</span>,
    },
    {
      clave: 'mensaje',
      encabezado: 'Mensaje',
      ocultarEnMovil: true,
      celda: (s) => <span className="text-sm text-muted">{truncate(s.mensaje, 60) || '—'}</span>,
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader titulo="Lotes" descripcion="Consultas masivas en e-SATJE a partir de un Excel" acciones={nuevoLote} />

      <nav aria-label="Filtrar por estado" className="flex flex-wrap gap-2">
        <FiltroEstado href="/lotes" activo={estado === null}>
          Todos
        </FiltroEstado>
        {Object.entries(ESTADO_ETIQUETAS).map(([clave, etiqueta]) => (
          <FiltroEstado key={clave} href={`/lotes?estado=${clave}`} activo={estado === clave}>
            {etiqueta}
          </FiltroEstado>
        ))}
      </nav>

      {error ? (
        <Alert tono="peligro" rol="alert">
          No se pudo cargar la lista de lotes.
        </Alert>
      ) : (
        <DataTable
          etiqueta="Lotes"
          columnas={columnas}
          filas={solicitudes}
          claveFila={(s) => s.id}
          vacio={
            estado ? (
              <EmptyState
                titulo="No hay lotes con este estado"
                accion={
                  <ButtonLink href="/lotes" variante="secundario">
                    Ver todos
                  </ButtonLink>
                }
              />
            ) : (
              <EmptyState
                titulo="Aún no hay lotes"
                descripcion="Sube un Excel para lanzar tu primera consulta."
                accion={nuevoLote}
              />
            )
          }
        />
      )}
    </div>
  )
}
