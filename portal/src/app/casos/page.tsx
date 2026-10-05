import { createClient } from '@/lib/supabase/server'
import Link from 'next/link'
import { formatFecha } from '@/lib/fechas'
import {
  COLUMNAS_EXPEDIENTE_LISTA,
  ESTADOS_CASO,
  ESTADO_ETIQUETAS,
  type ExpedienteLista,
} from '@/lib/casos'
import { traducirErrorInterno } from '@/lib/lotes'

const POR_PAGINA = 50

type SearchParams = {
  q?: string
  estado?: string
  fase?: string
  ciudad?: string
  pendientes?: string
  page?: string
}

function validarPage(page: string | undefined): number {
  const n = parseInt(page ?? '1', 10)
  return Number.isNaN(n) || n < 1 ? 1 : n
}

function escapeIlike(valor: string): string {
  return valor.replace(/[%_]/g, (c) => `\\${c}`)
}

async function getExpedientes(
  supabase: Awaited<ReturnType<typeof createClient>>,
  params: SearchParams
): Promise<{ data: ExpedienteLista[]; count: number; error: string | null }> {
  const page = validarPage(params.page)
  const from = (page - 1) * POR_PAGINA
  const to = from + POR_PAGINA - 1

  let query = supabase
    .from('expedientes')
    .select(COLUMNAS_EXPEDIENTE_LISTA, { count: 'exact' })
    .order('actualizado_en', { ascending: false })
    .range(from, to)

  if (params.q) {
    const q = escapeIlike(params.q.slice(0, 60))
    query = query.ilike('numero_causa', `%${q}%`)
  }

  if (params.estado && ESTADOS_CASO.includes(params.estado as (typeof ESTADOS_CASO)[number])) {
    query = query.eq('estado', params.estado)
  }

  if (params.fase) {
    query = query.eq('fase_actual', params.fase)
  }

  if (params.ciudad) {
    query = query.ilike('ciudad', `%${params.ciudad}%`)
  }

  if (params.pendientes === '1') {
    const { data: pendientes, error: pendError } = await supabase
      .from('revisiones_ia')
      .select('numero_causa')
      .eq('estado', 'PENDIENTE')

    if (pendError) {
      console.error('Error consultando revisiones pendientes:', pendError)
      return { data: [], count: 0, error: 'Error al filtrar por revisiones pendientes' }
    }

    const causales = pendientes?.map((r) => r.numero_causa) ?? []
    if (causales.length === 0) {
      return { data: [], count: 0, error: null }
    }
    query = query.in('numero_causa', causales)
  }

  const { data, error, count } = await query

  if (error) {
    console.error('Error fetching expedientes:', error)
    return { data: [], count: 0, error: traducirErrorInterno(error.message) }
  }

  return { data: data as ExpedienteLista[], count: count ?? 0, error: null }
}

function buildUrl(base: string, params: SearchParams, newPage: number): string {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.estado) sp.set('estado', params.estado)
  if (params.fase) sp.set('fase', params.fase)
  if (params.ciudad) sp.set('ciudad', params.ciudad)
  if (params.pendientes === '1') sp.set('pendientes', '1')
  sp.set('page', String(newPage))
  return `${base}?${sp.toString()}`
}

async function CasosList({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams
  const supabase = await createClient()

  const { data, count, error } = await getExpedientes(supabase, params)
  const page = validarPage(params.page)
  const totalPages = Math.ceil((count ?? 0) / POR_PAGINA)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">Casos</h1>

      <form method="get" className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div className="sm:col-span-2 lg:col-span-2">
            <label htmlFor="q" className="block text-sm font-medium text-gray-700">Buscar por número de causa</label>
            <input
              id="q"
              name="q"
              type="text"
              value={params.q ?? ''}
              placeholder="Ej: 17230-2019"
              maxLength={60}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="estado" className="block text-sm font-medium text-gray-700">Estado</label>
            <select
              id="estado"
              name="estado"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Todos</option>
              {ESTADOS_CASO.map((e) => (
                <option key={e} value={e} selected={params.estado === e}>
                  {e}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="fase" className="block text-sm font-medium text-gray-700">Fase actual</label>
            <input
              id="fase"
              name="fase"
              type="text"
              value={params.fase ?? ''}
              placeholder="Ej: 1.1"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="ciudad" className="block text-sm font-medium text-gray-700">Ciudad</label>
            <input
              id="ciudad"
              name="ciudad"
              type="text"
              value={params.ciudad ?? ''}
              placeholder="Ej: Quito"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                name="pendientes"
                type="checkbox"
                value="1"
                checked={params.pendientes === '1'}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <span className="text-sm text-gray-900">Solo con revisión pendiente</span>
            </label>
          </div>
        </div>
        <div className="flex gap-2">
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
          {error}
        </div>
      )}

      <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
        {data.length === 0 && !error ? (
          <div className="p-12 text-center text-gray-500">
            No hay causas con estos filtros
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Número de causa</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Ciudad</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Estado</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Etapa actual</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Fase actual</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Inicio fase actual</th>
                    <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Actualizado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {data.map((c) => (
                    <tr key={c.numero_causa} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-sm text-gray-900">
                        <Link
                          href={`/casos/${encodeURIComponent(c.numero_causa)}`}
                          className="text-blue-600 hover:text-blue-900"
                        >
                          {c.numero_causa}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.ciudad ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${c.estado && ESTADO_ETIQUETAS[c.estado] ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                          {c.estado ? (ESTADO_ETIQUETAS[c.estado] ?? c.estado) : '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.etapa_actual ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{c.fase_actual ?? '-'}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(c.fecha_inicio_fase_actual)}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(c.actualizado_en)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="border-t border-gray-200 px-4 py-3 flex items-center justify-between">
                <p className="text-sm text-gray-500">
                  Página {page} de {totalPages} — {count} resultados
                </p>
                <div className="flex gap-2">
                  {page > 1 && (
                    <Link
                      href={buildUrl('/casos', params, page - 1)}
                      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Anterior
                    </Link>
                  )}
                  {page < totalPages && (
                    <Link
                      href={buildUrl('/casos', params, page + 1)}
                      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Siguiente
                    </Link>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default async function CasosPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return <CasosList searchParams={searchParams} />
}