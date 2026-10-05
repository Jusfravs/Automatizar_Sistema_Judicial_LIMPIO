import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
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

const CLASE_CAMPO =
  'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500'

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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">Casos</h1>

      {/* El key reinicia los valores por defecto al limpiar o cambiar de filtros. */}
      <form
        key={`${f.q}|${f.estado}|${f.fase}|${f.ciudad}|${f.pendientes}`}
        method="get"
        className="space-y-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="q" className="block text-sm font-medium text-gray-700">Número de causa</label>
            <input id="q" name="q" type="text" defaultValue={f.q} maxLength={60} placeholder="Ej: 17230-2019" className={CLASE_CAMPO} />
          </div>
          <div>
            <label htmlFor="estado" className="block text-sm font-medium text-gray-700">Estado</label>
            <select id="estado" name="estado" defaultValue={f.estado} className={CLASE_CAMPO}>
              <option value="">Todos</option>
              {ESTADOS_CASO.map((e) => (
                <option key={e} value={e}>{ESTADO_CASO_ETIQUETAS[e] ?? e}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="fase" className="block text-sm font-medium text-gray-700">Fase actual</label>
            <select id="fase" name="fase" defaultValue={f.fase} className={CLASE_CAMPO}>
              <option value="">Todas</option>
              {nombresFase.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ciudad" className="block text-sm font-medium text-gray-700">Ciudad</label>
            <input id="ciudad" name="ciudad" type="text" defaultValue={f.ciudad} maxLength={60} placeholder="Ej: Quito" className={CLASE_CAMPO} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <input
              id="pendientes"
              name="pendientes"
              type="checkbox"
              value="1"
              defaultChecked={f.pendientes}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="pendientes" className="text-sm text-gray-900">Solo con revisión pendiente</label>
          </div>
          <button
            type="submit"
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Filtrar
          </button>
          <Link
            href="/casos"
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Limpiar
          </Link>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          No se pudieron cargar las causas. Intenta de nuevo en unos segundos.
        </div>
      )}

      {!error && (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          {filas.length === 0 ? (
            <p className="p-12 text-center text-gray-500">No hay causas con estos filtros.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="bg-gray-50">
                  <tr>
                    {['Número de causa', 'Ciudad', 'Estado', 'Etapa actual', 'Fase actual', 'Inicio fase actual', 'Actualizado'].map((t) => (
                      <th key={t} scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filas.map((c) => (
                    <tr key={c.numero_causa} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-sm">
                        <Link href={`/casos/${encodeURIComponent(c.numero_causa)}`} className="text-blue-600 hover:text-blue-900">
                          {c.numero_causa}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.ciudad ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.estado ? (ESTADO_CASO_ETIQUETAS[c.estado] ?? c.estado) : '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.etapa_actual ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.fase_actual ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{formatFechaProcesal(c.fecha_inicio_fase_actual)}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(c.actualizado_en)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <nav aria-label="Paginación de casos" className="flex items-center justify-between border-t border-gray-200 px-4 py-3">
            <p className="text-sm text-gray-500">Página {f.page} de {totalPaginas} · {total} causas</p>
            <div className="flex gap-2">
              {f.page > 1 && (
                <Link href={urlPagina(f, f.page - 1)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Anterior
                </Link>
              )}
              {f.page < totalPaginas && (
                <Link href={urlPagina(f, f.page + 1)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Siguiente
                </Link>
              )}
            </div>
          </nav>
        </div>
      )}
    </div>
  )
}
