import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import {
  Alert,
  ButtonLink,
  DataTable,
  EmptyState,
  EstadoBadge,
  PageHeader,
  Pagination,
  type Columna,
} from '@/components/ui'
import { IconoCerrar } from '@/components/ui/iconos'
import { FOCO } from '@/components/ui/estilos'
import { NumeroCausaCompartido } from '@/components/NumeroCausa'
import { cx } from '@/lib/cx'
import { NAVEGACION } from '@/lib/transiciones'
import { formatFecha, formatFechaProcesal } from '@/lib/fechas'
import {
  CASOS_POR_PAGINA,
  COLUMNAS_EXPEDIENTE_LISTA,
  ESTADOS_CASO,
  ESTADO_CASO_ETIQUETAS,
  escaparIlike,
  leerPagina,
  primerValor,
  type ExpedienteLista,
} from '@/lib/casos'
import { FiltrosCasos } from './FiltrosCasos'
import { FlechaOrden } from './FlechaOrden'

type SearchParams = Record<string, string | string[] | undefined>

/** Columnas por las que se puede ordenar y su dirección inicial al elegirlas. */
const ORDENABLES = {
  causa: { columna: 'numero_causa', inicial: 'asc' },
  estado: { columna: 'estado', inicial: 'asc' },
  fase: { columna: 'fase_actual', inicial: 'asc' },
  inicio: { columna: 'fecha_inicio_fase_actual', inicial: 'desc' },
  actualizado: { columna: 'actualizado_en', inicial: 'desc' },
} as const
type ClaveOrden = keyof typeof ORDENABLES
type Direccion = 'asc' | 'desc'
type Orden = { clave: ClaveOrden; dir: Direccion }
const ORDEN_DEFECTO: Orden = { clave: 'actualizado', dir: 'desc' }

type Filtros = {
  q: string
  estado: string
  fase: string
  ciudad: string
  pendientes: boolean
  orden: Orden
  page: number
}

function leerOrden(valor: string): Orden {
  const [clave, dir] = valor.split('-')
  if (clave in ORDENABLES && (dir === 'asc' || dir === 'desc')) return { clave: clave as ClaveOrden, dir }
  return ORDEN_DEFECTO
}

/** "" para el orden por defecto: la URL limpia significa "lo de siempre". */
function textoOrden(o: Orden): string {
  return o.clave === ORDEN_DEFECTO.clave && o.dir === ORDEN_DEFECTO.dir ? '' : `${o.clave}-${o.dir}`
}

function leerFiltros(sp: SearchParams): Filtros {
  const estado = primerValor(sp.estado)
  return {
    q: primerValor(sp.q).slice(0, 60),
    estado: ESTADOS_CASO.includes(estado) ? estado : '',
    fase: primerValor(sp.fase).slice(0, 80),
    ciudad: primerValor(sp.ciudad).slice(0, 60),
    pendientes: primerValor(sp.pendientes) === '1',
    orden: leerOrden(primerValor(sp.orden)),
    page: leerPagina(primerValor(sp.page)),
  }
}

function urlPagina(f: Filtros, page: number): string {
  const sp = new URLSearchParams()
  if (f.q) sp.set('q', f.q)
  if (f.estado) sp.set('estado', f.estado)
  if (f.fase) sp.set('fase', f.fase)
  if (f.ciudad) sp.set('ciudad', f.ciudad)
  if (f.pendientes) sp.set('pendientes', '1')
  const orden = textoOrden(f.orden)
  if (orden) sp.set('orden', orden)
  if (page > 1) sp.set('page', String(page))
  const consulta = sp.toString()
  return consulta ? `/casos?${consulta}` : '/casos'
}

type Resultado = { filas: ExpedienteLista[]; total: number; error: boolean }

async function buscarCasos(f: Filtros, fasesValidas: string[]): Promise<Resultado> {
  const supabase = await createClient()
  const desde = (f.page - 1) * CASOS_POR_PAGINA

  let causasPendientes: string[] | null = null
  if (f.pendientes) {
    const { data, error } = await supabase.from('revisiones_ia').select('numero_causa').eq('estado', 'PENDIENTE')
    if (error) {
      console.error('No se pudieron leer las revisiones pendientes:', error.message)
      return { filas: [], total: 0, error: true }
    }
    causasPendientes = [...new Set((data ?? []).map((r) => r.numero_causa))]
    if (causasPendientes.length === 0) return { filas: [], total: 0, error: false }
  }

  const { columna } = ORDENABLES[f.orden.clave]
  let consulta = supabase
    .from('expedientes')
    .select(COLUMNAS_EXPEDIENTE_LISTA, { count: 'exact' })
    .order(columna, { ascending: f.orden.dir === 'asc', nullsFirst: false })
    // Desempate estable: la paginación no repite ni salta causas con el mismo valor.
    .order('numero_causa', { ascending: true })
    .range(desde, desde + CASOS_POR_PAGINA - 1)

  if (f.q) consulta = consulta.ilike('numero_causa', `%${escaparIlike(f.q)}%`)
  if (f.estado) consulta = consulta.eq('estado', f.estado)
  if (f.fase && fasesValidas.includes(f.fase)) consulta = consulta.eq('fase_actual', f.fase)
  if (f.ciudad) consulta = consulta.ilike('ciudad', `%${escaparIlike(f.ciudad)}%`)
  if (causasPendientes) consulta = consulta.in('numero_causa', causasPendientes)

  const { data, error, count } = await consulta
  // Una página fuera de rango no es un error: simplemente no tiene filas.
  if (error?.code === 'PGRST103') return { filas: [], total: count ?? 0, error: false }
  if (error) {
    console.error('No se pudieron leer las causas:', error.message)
    return { filas: [], total: 0, error: true }
  }
  return { filas: (data ?? []) as ExpedienteLista[], total: count ?? 0, error: false }
}

function urlSin(f: Filtros, quitar: 'q' | 'estado' | 'fase' | 'ciudad' | 'pendientes'): string {
  const sinFiltro: Filtros = { ...f, [quitar]: quitar === 'pendientes' ? false : '' }
  return urlPagina(sinFiltro, 1)
}

function Chip({ texto, href }: { texto: string; href: string }) {
  return (
    <Link
      href={href}
      scroll={false}
      className={`inline-flex items-center gap-1.5 rounded-full border border-subtle bg-surface px-3 py-1 text-sm text-fg transition-colors hover:bg-surface-2 ${FOCO}`}
    >
      {texto}
      <IconoCerrar className="size-3.5 shrink-0 text-muted" />
      <span className="sr-only">(quitar filtro)</span>
    </Link>
  )
}

/** Dirección que muestra la flecha: la actual si la columna está activa. */
function siguienteAscendente(activa: boolean, f: Filtros, clave: ClaveOrden): boolean {
  return activa ? f.orden.dir === 'asc' : ORDENABLES[clave].inicial === 'asc'
}

/** Cabecera ordenable: enlace que alterna la dirección; la flecha y aria-sort dicen el estado. */
function EncabezadoOrden({ etiqueta, clave, f }: { etiqueta: string; clave: ClaveOrden; f: Filtros }) {
  const activa = f.orden.clave === clave
  const siguiente: Orden = activa
    ? { clave, dir: f.orden.dir === 'asc' ? 'desc' : 'asc' }
    : { clave, dir: ORDENABLES[clave].inicial }
  return (
    <Link
      href={urlPagina({ ...f, orden: siguiente }, 1)}
      scroll={false}
      className={cx(
        'group/orden -mx-1 inline-flex items-center gap-1 rounded-sm px-1 uppercase transition-colors hover:text-fg',
        activa && 'text-fg',
        FOCO,
      )}
    >
      {etiqueta}
      <FlechaOrden activa={activa} ascendente={siguienteAscendente(activa, f, clave)} />
      <span className="sr-only">
        {activa ? `, orden ${f.orden.dir === 'asc' ? 'ascendente' : 'descendente'}; cambiar` : ', ordenar'}
      </span>
    </Link>
  )
}

/** Fase arriba y etapa debajo, igual para el último hito y para el estado actual. */
function FaseEtapa({ fase, etapa }: { fase: string | null; etapa: string | null }) {
  return (
    <div className="min-w-0 text-sm">
      <p className="text-fg">{fase ?? '—'}</p>
      {etapa ? <p className="text-xs text-muted">{etapa}</p> : null}
    </div>
  )
}

function columnas(f: Filtros): Columna<ExpedienteLista>[] {
  const orden = (clave: ClaveOrden) =>
    f.orden.clave === clave ? (f.orden.dir === 'asc' ? 'ascending' : 'descending') : undefined
  return [
    {
      clave: 'causa',
      encabezado: <EncabezadoOrden etiqueta="Número de causa" clave="causa" f={f} />,
      etiqueta: 'Número de causa',
      orden: orden('causa'),
      principal: true,
      celda: (c, vista) => (
        <Link
          href={`/casos/${encodeURIComponent(c.numero_causa)}`}
          transitionTypes={NAVEGACION}
          className={`whitespace-nowrap rounded-sm font-mono text-sm font-medium text-fg underline-offset-2 transition-colors hover:text-primary hover:underline ${FOCO}`}
        >
          {/* Solo en la tabla: el nombre de la transición debe ser único en la página. */}
          {vista === 'tabla' ? (
            <NumeroCausaCompartido numero={c.numero_causa}>{c.numero_causa}</NumeroCausaCompartido>
          ) : (
            c.numero_causa
          )}
        </Link>
      ),
    },
    {
      clave: 'estado',
      encabezado: <EncabezadoOrden etiqueta="Estado" clave="estado" f={f} />,
      etiqueta: 'Estado',
      orden: orden('estado'),
      celda: (c) => (c.estado ? <EstadoBadge tipo="caso" estado={c.estado} /> : <span className="text-muted">—</span>),
    },
    { clave: 'ciudad', encabezado: 'Ciudad', celda: (c) => <span className="text-sm">{c.ciudad ?? '—'}</span> },
    {
      clave: 'hito',
      encabezado: 'Último hito',
      etiqueta: 'Último hito',
      celda: (c) => <FaseEtapa fase={c.ultima_fase} etapa={c.ultima_etapa} />,
    },
    {
      clave: 'fase',
      encabezado: <EncabezadoOrden etiqueta="Etapa y fase actual" clave="fase" f={f} />,
      etiqueta: 'Etapa y fase actual',
      orden: orden('fase'),
      celda: (c) => <FaseEtapa fase={c.fase_actual} etapa={c.etapa_actual} />,
    },
    {
      clave: 'inicio',
      encabezado: <EncabezadoOrden etiqueta="Inicio fase actual" clave="inicio" f={f} />,
      etiqueta: 'Inicio fase actual',
      orden: orden('inicio'),
      ocultarEnMovil: true,
      celda: (c) => <span className="whitespace-nowrap text-sm tabular-nums text-muted">{formatFechaProcesal(c.fecha_inicio_fase_actual)}</span>,
    },
    {
      clave: 'actualizado',
      encabezado: <EncabezadoOrden etiqueta="Actualizado" clave="actualizado" f={f} />,
      etiqueta: 'Actualizado',
      orden: orden('actualizado'),
      ocultarEnMovil: true,
      celda: (c) => <span className="whitespace-nowrap text-sm tabular-nums text-muted">{formatFecha(c.actualizado_en)}</span>,
    },
  ]
}

export const metadata = { title: 'Casos' }

export default async function CasosPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const f = leerFiltros(await searchParams)
  const supabase = await createClient()
  const { data: fasesCatalogo, error: errorFases } = await supabase
    .from('catalogo_fases')
    .select('nombre')
    .order('fas_id')
  if (errorFases) console.error('No se pudo leer el catálogo de fases:', errorFases.message)
  const nombresFase = (fasesCatalogo ?? []).map((x) => x.nombre)

  const { filas, total, error } = await buscarCasos(f, nombresFase)
  const totalPaginas = Math.max(1, Math.ceil(total / CASOS_POR_PAGINA))

  // La clave es el tipo de filtro: al escribir, el chip cambia de texto sin salir y volver a entrar.
  const chips: { clave: string; texto: string; href: string }[] = []
  if (f.q) chips.push({ clave: 'q', texto: `Causa: ${f.q}`, href: urlSin(f, 'q') })
  if (f.estado) chips.push({ clave: 'estado', texto: `Estado: ${ESTADO_CASO_ETIQUETAS[f.estado] ?? f.estado}`, href: urlSin(f, 'estado') })
  if (f.fase) chips.push({ clave: 'fase', texto: `Fase: ${f.fase}`, href: urlSin(f, 'fase') })
  if (f.ciudad) chips.push({ clave: 'ciudad', texto: `Ciudad: ${f.ciudad}`, href: urlSin(f, 'ciudad') })
  if (f.pendientes) chips.push({ clave: 'pendientes', texto: 'Con revisión pendiente', href: urlSin(f, 'pendientes') })

  return (
    <div className="space-y-6">
      <PageHeader titulo="Casos" descripcion="Causas consultadas y su clasificación procesal" />

      <FiltrosCasos
        iniciales={{
          q: f.q,
          estado: f.estado,
          fase: f.fase,
          ciudad: f.ciudad,
          pendientes: f.pendientes,
          orden: textoOrden(f.orden),
        }}
        fases={nombresFase}
        estados={ESTADOS_CASO.map((e) => ({ valor: e, etiqueta: ESTADO_CASO_ETIQUETAS[e] ?? e }))}
        hayFiltros={chips.length > 0}
      >
        <div className="space-y-4">
          {chips.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">Filtros activos:</span>
              {chips.map((c) => (
                <Chip key={c.clave} texto={c.texto} href={c.href} />
              ))}
            </div>
          ) : null}

          {error ? (
            <Alert tono="peligro" rol="alert">
              No se pudieron cargar las causas. Intenta de nuevo en unos segundos.
            </Alert>
          ) : (
            <>
              <p className="text-sm text-muted" aria-live="polite">
                <span className="font-semibold tabular-nums text-fg">{total.toLocaleString('es-EC')}</span>{' '}
                {total === 1 ? 'causa' : 'causas'}
              </p>
              <DataTable
                etiqueta="Causas"
                columnas={columnas(f)}
                filas={filas}
                claveFila={(c) => c.numero_causa}
                vacio={
                  <EmptyState
                    titulo="No hay causas con estos filtros"
                    descripcion="Prueba con otro número, quita un filtro o revisa la ortografía de la ciudad."
                    accion={
                      chips.length > 0 ? (
                        <ButtonLink href="/casos" variante="secundario">
                          Quitar filtros
                        </ButtonLink>
                      ) : undefined
                    }
                  />
                }
              />
              <Pagination
                pagina={f.page}
                totalPaginas={totalPaginas}
                hrefPagina={(n) => urlPagina(f, n)}
                etiqueta="Paginación de casos"
              />
            </>
          )}
        </div>
      </FiltrosCasos>
    </div>
  )
}
