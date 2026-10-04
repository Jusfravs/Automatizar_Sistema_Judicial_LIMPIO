import { createClient } from '@/lib/supabase/server'
import ProtectedLayout from '@/app/protected-layout'
import Link from 'next/link'
import type { Database } from '@/lib/database.types'

type SolicitudLote = Database['public']['Tables']['solicitudes_lote']['Row']

const ESTADO_COLORES: Record<string, string> = {
  SOLICITADA: 'bg-yellow-100 text-yellow-800',
  TOMADA: 'bg-blue-100 text-blue-800',
  PREPARANDO: 'bg-purple-100 text-purple-800',
  EN_CURSO: 'bg-indigo-100 text-indigo-800',
  COMPLETADA: 'bg-green-100 text-green-800',
  FALLIDA: 'bg-red-100 text-red-800',
  RECHAZADA: 'bg-red-100 text-red-800',
  CANCELADA: 'bg-gray-100 text-gray-800',
}

const ESTADO_ETIQUETAS: Record<string, string> = {
  SOLICITADA: 'Solicitada',
  TOMADA: 'Tomada',
  PREPARANDO: 'Preparando',
  EN_CURSO: 'En curso',
  COMPLETADA: 'Completada',
  FALLIDA: 'Fallida',
  RECHAZADA: 'Rechazada',
  CANCELADA: 'Cancelada',
}

const MODO_ETIQUETAS: Record<string, string> = {
  solo: 'Una causa',
  lote: 'Lote de N causas',
  pendientes: 'Todas las pendientes',
}

async function getSolicitudes(): Promise<SolicitudLote[]> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('solicitudes_lote')
    .select('*')
    .order('creado_en', { ascending: false })

  if (error) {
    console.error('Error fetching solicitudes:', error)
    return []
  }

  return data || []
}

function formatFecha(fecha: string): string {
  try {
    return new Date(fecha).toLocaleString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return fecha
  }
}

function truncate(str: string | null, max: number): string {
  if (!str) return ''
  return str.length > max ? str.slice(0, max) + '…' : str
}

async function LotesList() {
  const solicitudes = await getSolicitudes()

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

      <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
        {solicitudes.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            No hay lotes creados. Haz clic en &ldquo;Nuevo lote&rdquo; para empezar.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" role="table">
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
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${ESTADO_COLORES[s.estado] || 'bg-gray-100 text-gray-800'}`}>
                        {ESTADO_ETIQUETAS[s.estado] || s.estado}
                      </span>
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
  return (
    <ProtectedLayout>
      <main className="p-6">
        <LotesList />
      </main>
    </ProtectedLayout>
  )
}