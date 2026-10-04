'use client'

import { useState, FormEvent } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20 MB

type Modo = 'solo' | 'lote' | 'pendientes'
type Filtros = {
  sucursal: string
  oficina: string
  estado_judicial: string
}

export default function NuevoLotePage() {
  const router = useRouter()
  const supabase = createClient()

  const [file, setFile] = useState<File | null>(null)
  const [hoja, setHoja] = useState('')
  const [filtros, setFiltros] = useState<Filtros>({
    sucursal: 'TODAS',
    oficina: '',
    estado_judicial: 'ACTIVO',
  })
  const [modo, setModo] = useState<Modo>('lote')
  const [parametro, setParametro] = useState('')
  const [trabajadores, setTrabajadores] = useState(2)
  const [continuar, setContinuar] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const modoValido = (): boolean => {
    if (modo === 'solo') return /^\d+$/.test(parametro.trim()) && parametro.trim().length > 0
    if (modo === 'lote') {
      const n = parseInt(parametro.trim(), 10)
      return !isNaN(n) && n >= 2 && n <= 100
    }
    return true
  }

  const trabajadoresValido = (): boolean => {
    if (modo === 'solo') return trabajadores === 1
    return trabajadores >= 1 && trabajadores <= 4
  }

  const validarFormulario = (): boolean => {
    if (!file) {
      setError('Debes seleccionar un archivo .xlsx')
      return false
    }
    if (file.type !== XLSX_MIME) {
      setError('El archivo debe ser .xlsx')
      return false
    }
    if (file.size > MAX_FILE_SIZE) {
      setError('El archivo no puede superar 20 MB')
      return false
    }
    if (modo !== 'pendientes' && !parametro.trim()) {
      setError('El parámetro es obligatorio para este modo')
      return false
    }
    if (!modoValido()) {
      setError(modo === 'solo' ? 'El número de causa debe ser un entero positivo' : 'El lote debe ser entre 2 y 100')
      return false
    }
    if (!trabajadoresValido()) {
      setError(modo === 'solo' ? 'Para "Una causa" los trabajadores deben ser 1' : 'Los trabajadores deben ser entre 1 y 4')
      return false
    }
    return true
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (!validarFormulario()) return
    setLoading(true)

    try {
      const id = crypto.randomUUID()
      const archivoRuta = `entradas/${id}.xlsx`

      // file is guaranteed to be non-null after validarFormulario()
      const fileToUpload = file!

      // Subir archivo a Storage
      const { error: uploadError } = await supabase.storage
        .from('lotes')
        .upload(archivoRuta, fileToUpload, {
          contentType: XLSX_MIME,
          upsert: false,
        })

      if (uploadError) {
        setError(`Error al subir archivo: ${uploadError.message}`)
        setLoading(false)
        return
      }

      // Preparar filtros JSONB
      const filtrosJson = {
        sucursal: filtros.sucursal,
        oficina: filtros.oficina,
        estado_judicial: filtros.estado_judicial,
      }

      // Insert en solicitudes_lote
      const { error: insertError } = await supabase
        .from('solicitudes_lote')
        .insert({
          id,
          archivo_ruta: archivoRuta,
          archivo_nombre: fileToUpload.name,
          hoja: hoja.trim() || null,
          filtros: filtrosJson,
          modo,
          parametro: modo === 'pendientes' ? null : parametro.trim(),
          trabajadores: modo === 'solo' ? 1 : trabajadores,
          continuar: modo === 'solo' ? false : continuar,
        })
        .select()

      if (insertError) {
        // Intentar borrar el archivo subido
        await supabase.storage.from('lotes').remove([archivoRuta])
        setError(`Error al crear el lote: ${insertError.message}`)
        setLoading(false)
        return
      }

      router.push(`/lotes/${id}`)
      router.refresh()
    } catch (err) {
      setError(`Error inesperado: ${err instanceof Error ? err.message : 'Error desconocido'}`)
      setLoading(false)
    }
  }

  return (
    <main className="p-6">
      <h1 className="mb-6 text-2xl font-semibold text-gray-900">Nuevo lote</h1>

      {error && (
        <div className="mb-6 rounded bg-red-50 p-4 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Archivo Excel</h2>
          <div className="space-y-2">
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
              disabled={loading}
              className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500">
              Solo .xlsx, máximo 20 MB. Hoja opcional: se usa la primera si se deja vacía.
            </p>
            {file && (
              <p className="text-sm text-gray-700">
                Seleccionado: <span className="font-medium">{file.name}</span> ({(file.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Hoja (opcional)</h2>
          <input
            type="text"
            value={hoja}
            onChange={(e) => setHoja(e.target.value)}
            placeholder="Nombre de la hoja (vacío = primera)"
            disabled={loading}
            className="w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Filtros</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">Sucursal</label>
              <input
                type="text"
                value={filtros.sucursal}
                onChange={(e) => setFiltros({ ...filtros, sucursal: e.target.value })}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Oficina</label>
              <input
                type="text"
                value={filtros.oficina}
                onChange={(e) => setFiltros({ ...filtros, oficina: e.target.value })}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Estado judicial</label>
              <input
                type="text"
                value={filtros.estado_judicial}
                onChange={(e) => setFiltros({ ...filtros, estado_judicial: e.target.value })}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-medium text-gray-900">Modo de ejecución</h2>
          <div className="space-y-4">
            <div className="flex gap-6">
              {(['lote', 'solo', 'pendientes'] as Modo[]).map((m) => (
                <label key={m} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="modo"
                    value={m}
                    checked={modo === m}
                    onChange={() => {
                      setModo(m)
                      if (m === 'solo') {
                        setTrabajadores(1)
                        setContinuar(false)
                      } else if (m === 'pendientes') {
                        setTrabajadores(2)
                        setContinuar(false)
                      }
                    }}
                    disabled={loading}
                    className="h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-900">
                    {m === 'lote' && 'Lote de N causas'}
                    {m === 'solo' && 'Una causa'}
                    {m === 'pendientes' && 'Todas las pendientes'}
                  </span>
                </label>
              ))}
            </div>

            {modo !== 'pendientes' && (
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  {modo === 'lote' ? 'Número de causas (2-100)' : 'Número de causa'}
                </label>
                <input
                  type="text"
                  value={parametro}
                  onChange={(e) => setParametro(e.target.value)}
                  placeholder={modo === 'lote' ? 'Ej: 50' : 'Ej: 2024-001234'}
                  disabled={loading}
                  className="mt-1 block w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Trabajadores {modo === 'solo' ? '(fijo en 1)' : '(1-4)'}
              </label>
              <input
                type="number"
                min="1"
                max={modo === 'solo' ? 1 : 4}
                value={trabajadores}
                onChange={(e) => setTrabajadores(parseInt(e.target.value, 10) || 1)}
                disabled={loading || modo === 'solo'}
                className="mt-1 block w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {modo !== 'pendientes' && modo !== 'solo' && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={continuar}
                  onChange={(e) => setContinuar(e.target.checked)}
                  disabled={loading}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-900">Omitir causas ya procesadas (continuar)</span>
              </label>
            )}
          </div>
        </div>

        <div className="flex gap-4">
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creando lote...' : 'Crear lote'}
          </button>
          <Link
            href="/lotes"
            className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Cancelar
          </Link>
        </div>
      </form>
    </main>
  )
}