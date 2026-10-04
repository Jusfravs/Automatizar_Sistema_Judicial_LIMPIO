'use client'

import { useState, FormEvent, useId } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { XLSX_MIME, MAX_FILE_SIZE, MAX_ARCHIVO_NOMBRE, MAX_HOJA, FILTROS_DEFAULTS, traducirErrorInterno } from '@/lib/lotes'

type Modo = 'solo' | 'lote' | 'pendientes'
type Filtros = {
  sucursal: string
  oficina: string
  estado_judicial: string
}

export default function NuevoLoteForm() {
  const router = useRouter()
  const supabase = createClient()

  const errorId = useId()

  const [file, setFile] = useState<File | null>(null)
  const [hoja, setHoja] = useState('')
  const [filtros, setFiltros] = useState<Filtros>({
    sucursal: FILTROS_DEFAULTS.sucursal,
    oficina: FILTROS_DEFAULTS.oficina,
    estado_judicial: FILTROS_DEFAULTS.estado_judicial,
  })
  const [modo, setModo] = useState<Modo>('lote')
  const [parametro, setParametro] = useState('')
  const [trabajadores, setTrabajadores] = useState(2)
  const [continuar, setContinuar] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof Filtros | 'file' | 'hoja' | 'parametro' | 'trabajadores', string>>>({})

  const validateField = (name: string, value: string | File | number | boolean | null): string | undefined => {
    switch (name) {
      case 'file':
        if (!value) return 'Debes seleccionar un archivo .xlsx'
        const f = value as File
        const validType = f.type === XLSX_MIME || f.type === ''
        const validExt = f.name.toLowerCase().endsWith('.xlsx')
        if (!validType || !validExt) return 'El archivo debe ser .xlsx'
        if (f.size > MAX_FILE_SIZE) return 'El archivo no puede superar 20 MB'
        return undefined
      case 'hoja':
        if (typeof value === 'string' && value.length > MAX_HOJA) return `La hoja no puede superar ${MAX_HOJA} caracteres`
        return undefined
      case 'sucursal':
        if (typeof value === 'string' && !value.trim()) return 'La sucursal no puede estar vacía'
        return undefined
      case 'parametro':
        if (modo !== 'pendientes' && typeof value === 'string' && !value.trim()) return 'El parámetro es obligatorio para este modo'
        if (modo === 'solo' && typeof value === 'string' && (value.trim().length < 1 || value.trim().length > 60)) return 'El número de causa debe tener entre 1 y 60 caracteres'
        if (modo === 'lote' && typeof value === 'string' && (!/^[0-9]{1,3}$/.test(value.trim()) || +value.trim() < 2 || +value.trim() > 100)) return 'El lote debe ser un número entre 2 y 100'
        return undefined
      case 'trabajadores':
        if (typeof value === 'number' && (value < 1 || value > 4)) return 'Los trabajadores deben ser entre 1 y 4'
        return undefined
      case 'archivo_nombre':
        if (typeof value === 'string' && value.length > MAX_ARCHIVO_NOMBRE) return `El nombre del archivo no puede superar ${MAX_ARCHIVO_NOMBRE} caracteres`
        return undefined
      default:
        return undefined
    }
  }

  const clearFieldError = (name: string) => {
    setFieldErrors((prev) => {
      const next = { ...prev }
      delete next[name as keyof typeof next]
      return next
    })
  }

  const validarFormulario = (): boolean => {
    let hasError = false
    const newErrors: typeof fieldErrors = {}

    const fileError = validateField('file', file)
    if (fileError) { newErrors.file = fileError; hasError = true }

    const hojaError = validateField('hoja', hoja)
    if (hojaError) { newErrors.hoja = hojaError; hasError = true }

    const sucursalError = validateField('sucursal', filtros.sucursal)
    if (sucursalError) { newErrors.sucursal = sucursalError; hasError = true }

    const archivoNombreError = validateField('archivo_nombre', file?.name ?? '')
    if (archivoNombreError) { newErrors.file = archivoNombreError; hasError = true }

    const parametroError = validateField('parametro', parametro)
    if (parametroError) { newErrors.parametro = parametroError; hasError = true }

    const trabajadoresError = validateField('trabajadores', trabajadores)
    if (trabajadoresError) { newErrors.trabajadores = trabajadoresError; hasError = true }

    setFieldErrors(newErrors)
    if (hasError) setError('Revisa los campos marcados')
    return !hasError
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (!validarFormulario()) {
      const firstError = Object.values(fieldErrors)[0]
      if (firstError) {
        const firstField = Object.keys(fieldErrors)[0]
        const el = document.getElementById(firstField)
        el?.focus()
      }
      return
    }
    setLoading(true)

    try {
      const id = crypto.randomUUID()
      const archivoRuta = `entradas/${id}.xlsx`
      let uploadOk = false

      try {
        const fileToUpload = file!
        const { error: uploadError } = await supabase.storage
          .from('lotes')
          .upload(archivoRuta, fileToUpload, {
            contentType: XLSX_MIME,
            upsert: false,
          })

        if (uploadError) {
          setError(traducirErrorInterno(uploadError.message))
          setLoading(false)
          return
        }
        uploadOk = true
      } catch (err) {
        setError(traducirErrorInterno(err instanceof Error ? err.message : 'Error al subir archivo'))
        setLoading(false)
        return
      }

      const filtrosJson = {
        sucursal: filtros.sucursal,
        oficina: filtros.oficina,
        estado_judicial: filtros.estado_judicial,
      }

      const { error: insertError } = await supabase
        .from('solicitudes_lote')
        .insert({
          id,
          archivo_ruta: archivoRuta,
          archivo_nombre: file!.name,
          hoja: hoja.trim() || null,
          filtros: filtrosJson,
          modo,
          parametro: modo === 'pendientes' ? null : parametro.trim(),
          trabajadores,
          continuar,
        })
        .select()

      if (insertError) {
        if (uploadOk) {
          try {
            await supabase.storage.from('lotes').remove([archivoRuta])
          } catch (cleanupErr) {
            console.warn('No se pudo limpiar archivo huérfano:', cleanupErr)
          }
        }
        setError(traducirErrorInterno(insertError.message))
        setLoading(false)
        return
      }

      router.push(`/lotes/${id}`)
      router.refresh()
    } catch (err) {
      console.error('Error inesperado:', err)
      setError('No se pudo completar la operación')
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-6" noValidate>
      {error && (
        <div id={errorId} className="mb-6 rounded bg-red-50 p-4 text-sm text-red-700" role="alert" aria-live="assertive">
          {error}
        </div>
      )}

      <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <legend className="mb-4 text-lg font-medium text-gray-900">Archivo Excel</legend>
        <div className="space-y-2">
          <input
            id="file"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              clearFieldError('file')
            }}
            required
            disabled={loading}
            aria-invalid={!!fieldErrors.file}
            aria-describedby={fieldErrors.file ? `${errorId}-file` : undefined}
            className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {fieldErrors.file && (
            <p id={`${errorId}-file`} className="text-sm text-red-600" role="alert">{fieldErrors.file}</p>
          )}
          <p className="text-xs text-gray-500">
            Solo .xlsx, máximo 20 MB. Hoja opcional: se usa la primera si se deja vacía.
          </p>
          {file && (
            <p className="text-sm text-gray-700">
              Seleccionado: <span className="font-medium">{file.name}</span> ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </p>
          )}
        </div>
      </fieldset>

      <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <legend className="mb-4 text-lg font-medium text-gray-900">Hoja (opcional)</legend>
        <input
          id="hoja"
          type="text"
          value={hoja}
          onChange={(e) => { setHoja(e.target.value); clearFieldError('hoja') }}
          placeholder="Nombre de la hoja (vacío = primera)"
          maxLength={MAX_HOJA}
          disabled={loading}
          aria-invalid={!!fieldErrors.hoja}
          aria-describedby={fieldErrors.hoja ? `${errorId}-hoja` : undefined}
          className="w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        {fieldErrors.hoja && (
          <p id={`${errorId}-hoja`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.hoja}</p>
        )}
      </fieldset>

      <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <legend className="mb-4 text-lg font-medium text-gray-900">Filtros</legend>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="sucursal" className="block text-sm font-medium text-gray-700">Sucursal</label>
            <input
              id="sucursal"
              type="text"
              value={filtros.sucursal}
              onChange={(e) => { setFiltros({ ...filtros, sucursal: e.target.value }); clearFieldError('sucursal') }}
              disabled={loading}
              aria-invalid={!!fieldErrors.sucursal}
              aria-describedby={fieldErrors.sucursal ? `${errorId}-sucursal` : undefined}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {fieldErrors.sucursal && (
              <p id={`${errorId}-sucursal`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.sucursal}</p>
            )}
          </div>
          <div>
            <label htmlFor="oficina" className="block text-sm font-medium text-gray-700">Oficina</label>
            <input
              id="oficina"
              type="text"
              value={filtros.oficina}
              onChange={(e) => { setFiltros({ ...filtros, oficina: e.target.value }); clearFieldError('oficina') }}
              disabled={loading}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="estado_judicial" className="block text-sm font-medium text-gray-700">Estado judicial</label>
            <input
              id="estado_judicial"
              type="text"
              value={filtros.estado_judicial}
              onChange={(e) => { setFiltros({ ...filtros, estado_judicial: e.target.value }); clearFieldError('estado_judicial') }}
              disabled={loading}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <legend className="mb-4 text-lg font-medium text-gray-900">Modo de ejecución</legend>
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-gray-700">Selecciona el modo</legend>
            <div className="flex flex-wrap gap-6" role="radiogroup" aria-label="Modo de ejecución">
              {(['lote', 'solo', 'pendientes'] as Modo[]).map((m) => (
                <label key={m} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="modo"
                    value={m}
                    checked={modo === m}
                    onChange={() => {
                      setModo(m)
                      clearFieldError('parametro')
                      // No cambiar trabajadores al cambiar de modo
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
          </fieldset>

          {modo !== 'pendientes' && (
            <div>
              <label htmlFor="parametro" className="block text-sm font-medium text-gray-700">
                {modo === 'lote' ? 'Número de causas (2-100)' : 'Número de causa (ej: 17230-2019-01234)'}
              </label>
              <input
                id="parametro"
                type="text"
                value={parametro}
                onChange={(e) => { setParametro(e.target.value); clearFieldError('parametro') }}
                placeholder={modo === 'lote' ? 'Ej: 50' : 'Ej: 17230-2019-01234'}
                maxLength={modo === 'lote' ? 3 : 60}
                disabled={loading}
                aria-invalid={!!fieldErrors.parametro}
                aria-describedby={fieldErrors.parametro ? `${errorId}-parametro` : undefined}
                className="mt-1 block w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {fieldErrors.parametro && (
                <p id={`${errorId}-parametro`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.parametro}</p>
              )}
            </div>
          )}

          <div>
            <label htmlFor="trabajadores" className="block text-sm font-medium text-gray-700">
              Trabajadores (1-4)
            </label>
            <input
              id="trabajadores"
              type="number"
              min="1"
              max="4"
              value={trabajadores}
              onChange={(e) => { setTrabajadores(parseInt(e.target.value, 10) || 1); clearFieldError('trabajadores') }}
              disabled={loading}
              aria-invalid={!!fieldErrors.trabajadores}
              aria-describedby={fieldErrors.trabajadores ? `${errorId}-trabajadores` : undefined}
              className="mt-1 block w-full max-w-xs rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {fieldErrors.trabajadores && (
              <p id={`${errorId}-trabajadores`} className="mt-1 text-sm text-red-600" role="alert">{fieldErrors.trabajadores}</p>
            )}
          </div>

          {modo !== 'solo' && (
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
      </fieldset>

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
  )
}