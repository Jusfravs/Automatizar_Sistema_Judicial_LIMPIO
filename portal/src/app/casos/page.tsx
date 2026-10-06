import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import {
  Alert,
  Button,
  ButtonLink,
  Checkbox,
  DataTable,
  EmptyState,
  EstadoBadge,
  Field,
  Input,
  PageHeader,
  Pagination,
  Select,
  type Columna,
} from '@/components/ui'
import { IconoCerrar } from '@/components/ui/iconos'
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

type SearchParams = Record<string, string | string[] | undefined>

type Filtros = {
  q: string
  estado: string
  fase: string
  ciudad: string
  pendientes: boolean
  page: number
}

function leerFiltros(sp: SearchParams): Filtros {
  const estado = primerValor(sp.estado)
  return {
    q: primerValor(sp.q).slice(0, 60),
    estado: ESTADOS_CASO.includes(estado) ? estado : '',
    fase: primerValor(sp.fase).slice(0, 80),
    ciudad: primerValor(sp.ciudad).slice(0, 60),
    pendientes: primerValor(sp.pendientes) === '1',
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
  sp.set('page', String(page))
  return `/casos?${sp.toString()}`
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

  let consulta = supabase
    .from('expedientes')
    .select(COLUMNAS_EXPEDIENTE_LISTA, { count: 'exact' })
    .order('actualizado_en', { ascending: false })
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

function urlSin(f: Filtros, quitar: keyof Omit<Filtros, 'page'>): string {
  const sinFiltro: Filtros = { ...f, [quitar]: quitar === 'pendientes' ? false : '' }
  return urlPagina(sinFiltro, 1)
}

function Chip({ texto, href }: { texto: string; href: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 rounded-full border border-subtle bg-surface px-3 py-1 text-sm text-fg hover:bg-surface-2"
    >
      {texto}
      <IconoCerrar className="size-3.5 text-muted" />
      <span className="sr-only">(quitar filtro)</span>
    </Link>
  )
}

const COLUMNAS: Columna<ExpedienteLista>[] = [
  {
    clave: 'causa',
    encabezado: 'Número de causa',
    principal: true,
    celda: (c) => (
      <Link
        href={`/casos/${encodeURIComponent(c.numero_causa)}`}
        className="whitespace-nowrap font-mono text-sm font-medium text-fg hover:text-primary hover:underline"
      >
        {c.numero_causa}
      </Link>
    ),
  },
  {
    clave: 'estado',
    encabezado: 'Estado',
    celda: (c) => (c.estado ? <EstadoBadge tipo="caso" estado={c.estado} /> : <span className="text-muted">—</span>),
  },
  { clave: 'ciudad', encabezado: 'Ciudad', celda: (c) => <span className="text-sm">{c.ciudad ?? '—'}</span> },
  {
    clave: 'fase',
    encabezado: 'Etapa y fase actual',
    celda: (c) => (
      <div className="min-w-0 text-sm">
        <p className="text-fg">{c.fase_actual ?? '—'}</p>
        {c.etapa_actual ? <p className="text-xs text-muted">{c.etapa_actual}</p> : null}
      </div>
    ),
  },
  {
    clave: 'inicio',
    encabezado: 'Inicio fase actual',
    ocultarEnMovil: true,
    celda: (c) => <span className="text-sm tabular-nums text-muted">{formatFechaProcesal(c.fecha_inicio_fase_actual)}</span>,
  },
  {
    clave: 'actualizado',
    encabezado: 'Actualizado',
    ocultarEnMovil: true,
    celda: (c) => <span className="text-sm text-muted">{formatFecha(c.actualizado_en)}</span>,
  },
]

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

  const chips: { texto: string; href: string }[] = []
  if (f.q) chips.push({ texto: `Causa: ${f.q}`, href: urlSin(f, 'q') })
  if (f.estado) chips.push({ texto: `Estado: ${ESTADO_CASO_ETIQUETAS[f.estado] ?? f.estado}`, href: urlSin(f, 'estado') })
  if (f.fase) chips.push({ texto: `Fase: ${f.fase}`, href: urlSin(f, 'fase') })
  if (f.ciudad) chips.push({ texto: `Ciudad: ${f.ciudad}`, href: urlSin(f, 'ciudad') })
  if (f.pendientes) chips.push({ texto: 'Con revisión pendiente', href: urlSin(f, 'pendientes') })

  return (
    <div className="space-y-6">
      <PageHeader titulo="Casos" descripcion="Causas consultadas y su clasificación procesal" />

      {/* El key reinicia los valores por defecto al limpiar o cambiar de filtros. */}
      <form
        key={`${f.q}|${f.estado}|${f.fase}|${f.ciudad}|${f.pendientes}`}
        method="get"
        className="space-y-4 rounded-tarjeta bg-surface p-4 shadow-tarjeta"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Número de causa" htmlFor="q">
            <Input id="q" name="q" defaultValue={f.q} maxLength={60} placeholder="Ej.: 17230-2019" className="font-mono" />
          </Field>
          <Field label="Estado" htmlFor="estado">
            <Select id="estado" name="estado" defaultValue={f.estado}>
              <option value="">Todos</option>
              {ESTADOS_CASO.map((e) => (
                <option key={e} value={e}>
                  {ESTADO_CASO_ETIQUETAS[e] ?? e}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Fase actual" htmlFor="fase">
            <Select id="fase" name="fase" defaultValue={f.fase}>
              <option value="">Todas</option>
              {nombresFase.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Ciudad" htmlFor="ciudad">
            <Input id="ciudad" name="ciudad" defaultValue={f.ciudad} maxLength={60} placeholder="Ej.: Quito" />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Checkbox id="pendientes" name="pendientes" value="1" defaultChecked={f.pendientes} label="Solo con revisión pendiente" />
          <div className="flex gap-2 sm:ml-auto">
            <Button type="submit">Filtrar</Button>
            <ButtonLink href="/casos" variante="secundario">
              Limpiar
            </ButtonLink>
          </div>
        </div>
      </form>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">Filtros activos:</span>
          {chips.map((c) => (
            <Chip key={c.texto} {...c} />
          ))}
        </div>
      )}

      {error ? (
        <Alert tono="peligro" rol="alert">
          No se pudieron cargar las causas. Intenta de nuevo en unos segundos.
        </Alert>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            <span className="font-semibold tabular-nums text-fg">{total}</span> {total === 1 ? 'causa' : 'causas'}
          </p>
          <DataTable
            etiqueta="Causas"
            columnas={COLUMNAS}
            filas={filas}
            claveFila={(c) => c.numero_causa}
            vacio={
              <EmptyState
                titulo="No hay causas con estos filtros"
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
        </div>
      )}
    </div>
  )
}
