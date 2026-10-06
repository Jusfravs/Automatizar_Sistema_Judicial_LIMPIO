import { createClient } from '@/lib/supabase/server'
import Link from 'next/link'
import type { Database } from '@/lib/database.types'
import { formatFecha } from '@/lib/fechas'
import { MODO_ETIQUETAS } from '@/lib/lotes'
import { EstadoBadge } from '@/components/ui'

type SolicitudLote = Pick<
  Database['public']['Tables']['solicitudes_lote']['Row'],
  'id' | 'archivo_nombre' | 'modo' | 'parametro' | 'trabajadores' | 'estado' | 'creado_en' | 'mensaje'
>

async function getSolicitudes(): Promise<{ data: SolicitudLote[]; error: string | null }> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('id, archivo_nombre, modo, parametro, trabajadores, estado, creado_en, mensaje')
    .order('creado_en', { ascending: false })
    .limit(100)

  if (error) {
    console.error('Error fetching solicitudes:', error)
    return { data: [], error: 'No se pudo cargar la lista de lotes' }
  }

  return { data: data || [], error: null }
}

function truncate(str: string | null, max: number): string {
  if (!str) return ''
  return str.length > max ? str.slice(0, max) + '…' : str
}

async function LotesList() {
  const { data: solicitudes, error } = await getSolicitudes()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Lotes</h1>
        <Link
          href="/lotes/nuevo"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Nuevo lote
        </Link>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
        {solicitudes.length === 0 && !error ? (
          <div className="p-12 text-center text-gray-500">
            No hay lotes creados. Haz clic en &ldquo;Nuevo lote&rdquo; para empezar.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table>
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Archivo</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Modo</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Parámetro</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Trab.</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Estado</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Creado</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mensaje</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {solicitudes.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">{s.archivo_nombre}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{MODO_ETIQUETAS[s.modo] || s.modo}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 font-mono">{s.parametro || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{s.trabajadores}</td>
                    <td className="px-4 py-3">
                      <EstadoBadge tipo="lote" estado={s.estado} />
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatFecha(s.creado_en)}</td>
                    <td className="px-4 py-3 text-sm text-gray-500 max-w-xs truncate">{truncate(s.mensaje, 60)}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/lotes/${s.id}`}
                        className="text-sm font-medium text-blue-600 hover:text-blue-900"
                      >
                        Ver
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default async function LotesPage() {
  return <LotesList />
}