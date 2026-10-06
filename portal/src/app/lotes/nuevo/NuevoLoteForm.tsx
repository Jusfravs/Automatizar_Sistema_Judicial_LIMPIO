'use client'

import { useState, type FormEvent, type ReactNode } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { XLSX_MIME, MAX_FILE_SIZE, MAX_ARCHIVO_NOMBRE, MAX_HOJA, FILTROS_DEFAULTS, MODO_ETIQUETAS, traducirErrorInterno } from '@/lib/lotes'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { Checkbox } from '@/components/ui/Checkbox'
import { Field, a11yCampo } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { Radio } from '@/components/ui/Radio'
import { ZonaArchivo } from '@/components/ui/ZonaArchivo'

type Modo = 'solo' | 'lote' | 'pendientes'
type Filtros = {
  sucursal: string
  oficina: string
  estado_judicial: string
}

type CampoConError = keyof Filtros | 'file' | 'hoja' | 'parametro' | 'trabajadores'
const ORDEN_CAMPOS: CampoConError[] = ['file', 'hoja', 'sucursal', 'parametro', 'trabajadores']
const MODOS: readonly Modo[] = ['lote', 'solo', 'pendientes']

export default function NuevoLoteForm() {
  const router = useRouter()

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
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<CampoConError, string>>>({})

  const esSolo = modo === 'solo'
  const trabajadoresEfectivos = esSolo ? 1 : trabajadores
  const continuarEfectivo = esSolo ? false : continuar

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
        if (modo === 'solo' && typeof value === 'string' && value.trim().length > 60) return 'El número de causa no puede superar 60 caracteres'
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

  const validarFormulario = (): Partial<Record<CampoConError, string>> => {
    const errores: Partial<Record<CampoConError, string>> = {}
    const errorArchivo = validateField('file', file) ?? validateField('archivo_nombre', file?.name ?? '')
    if (errorArchivo) errores.file = errorArchivo
    const errorHoja = validateField('hoja', hoja)
    if (errorHoja) errores.hoja = errorHoja
    const errorSucursal = validateField('sucursal', filtros.sucursal)
    if (errorSucursal) errores.sucursal = errorSucursal
    const errorParametro = validateField('parametro', parametro)
    if (errorParametro) errores.parametro = errorParametro
    const errorTrabajadores = validateField('trabajadores', trabajadoresEfectivos)
    if (errorTrabajadores) errores.trabajadores = errorTrabajadores
    return errores
  }

  async function limpiarArchivoHuerfano(ruta: string) {
    const supabase = createClient()
    try {
      const { data, error: rmError } = await supabase.storage.from('lotes').remove([ruta])
      if (rmError || !data?.length) {
        console.warn('No se pudo limpiar el archivo huérfano:', rmError?.message ?? 'sin filas borradas')
      }
    } catch (err) {
      console.warn('No se pudo limpiar el archivo huérfano:', err)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    const errores = validarFormulario()
    setFieldErrors(errores)
    const primerCampo = ORDEN_CAMPOS.find((campo) => errores[campo])
    if (primerCampo) {
      setError('Revisa los campos marcados')
      document.getElementById(primerCampo)?.focus()
      return
    }

    setLoading(true)
    const supabase = createClient()
    const id = crypto.randomUUID()
    const archivoRuta = `entradas/${id}.xlsx`
    let archivoSubido = false

    try {
      const { error: uploadError } = await supabase.storage
        .from('lotes')
        .upload(archivoRuta, file!, { contentType: XLSX_MIME, upsert: false })
      if (uploadError) {
        console.error('No se pudo subir el archivo:', uploadError.message)
        setError(traducirErrorInterno(uploadError.message))
        setLoading(false)
        return
      }
      archivoSubido = true

      const { error: insertError } = await supabase.from('solicitudes_lote').insert({
        id,
        archivo_ruta: archivoRuta,
        archivo_nombre: file!.name,
        hoja: hoja.trim() || null,
        filtros: {
          sucursal: filtros.sucursal.trim(),
          oficina: filtros.oficina.trim(),
          estado_judicial: filtros.estado_judicial.trim(),
        },
        modo,
        parametro: modo === 'pendientes' ? null : parametro.trim(),
        trabajadores: trabajadoresEfectivos,
        continuar: continuarEfectivo,
      })
      if (insertError) {
        console.error('No se pudo crear la solicitud:', insertError.message)
        await limpiarArchivoHuerfano(archivoRuta)
        setError(traducirErrorInterno(insertError.message))
        setLoading(false)
        return
      }

      router.push(`/lotes/${id}`)
      router.refresh()
    } catch (err) {
      console.error('Error inesperado al crear el lote:', err)
      if (archivoSubido) await limpiarArchivoHuerfano(archivoRuta)
      setError('No se pudo completar la operación')
      setLoading(false)
    }
  }

  const ayudaParametro = modo === 'lote' ? 'Entre 2 y 100 causas del Excel.' : 'Ej.: 17230-2019-01234'
  const resumenFiltros = `Sucursal: ${filtros.sucursal.trim() || '—'} · Oficina: ${filtros.oficina.trim() || 'todas'} · Estado judicial: ${filtros.estado_judicial.trim() || '—'}`

  return (
    <form onSubmit={handleSubmit} className="max-w-3xl space-y-6" noValidate>
      <Seccion numero={1} titulo="Archivo Excel">
        <Field label="Archivo .xlsx" htmlFor="file" error={fieldErrors.file}>
          <ZonaArchivo
            {...a11yCampo('file', { error: fieldErrors.file })}
            archivo={file}
            alCambiar={(f) => {
              setFile(f)
              clearFieldError('file')
            }}
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            required
            disabled={loading}
            indicacion="Solo .xlsx, máximo 20 MB"
          />
        </Field>
        <Field label="Hoja (opcional)" htmlFor="hoja" ayuda="Si la dejas vacía se usa la primera hoja." error={fieldErrors.hoja}>
          <Input
            {...a11yCampo('hoja', { ayuda: true, error: fieldErrors.hoja })}
            value={hoja}
            onChange={(e) => {
              setHoja(e.target.value)
              clearFieldError('hoja')
            }}
            maxLength={MAX_HOJA}
            disabled={loading}
            className="max-w-xs"
          />
        </Field>
      </Seccion>

      <Seccion numero={2} titulo="Filtros">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Sucursal" htmlFor="sucursal" error={fieldErrors.sucursal}>
            <Input
              {...a11yCampo('sucursal', { error: fieldErrors.sucursal })}
              value={filtros.sucursal}
              onChange={(e) => {
                setFiltros({ ...filtros, sucursal: e.target.value })
                clearFieldError('sucursal')
              }}
              disabled={loading}
            />
          </Field>
          <Field label="Oficina" htmlFor="oficina">
            <Input
              id="oficina"
              value={filtros.oficina}
              onChange={(e) => setFiltros({ ...filtros, oficina: e.target.value })}
              disabled={loading}
            />
          </Field>
          <Field label="Estado judicial" htmlFor="estado_judicial">
            <Input
              id="estado_judicial"
              value={filtros.estado_judicial}
              onChange={(e) => setFiltros({ ...filtros, estado_judicial: e.target.value })}
              disabled={loading}
            />
          </Field>
        </div>
      </Seccion>

      <Seccion numero={3} titulo="Modo de ejecución">
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-muted">Qué causas consultar</legend>
          <div className="flex flex-wrap gap-x-6">
            {MODOS.map((m) => (
              <Radio
                key={m}
                name="modo"
                value={m}
                checked={modo === m}
                onChange={() => {
                  setModo(m)
                  clearFieldError('parametro')
                }}
                disabled={loading}
                label={MODO_ETIQUETAS[m]}
              />
            ))}
          </div>
        </fieldset>

        {modo === 'pendientes' && (
          <Alert tono="atencion" titulo="Corrida larga">
            Se consultarán todas las causas pendientes del Excel. Puede tardar varias horas y consume saldo de CAPTCHA.
          </Alert>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {modo !== 'pendientes' && (
            <Field
              label={modo === 'lote' ? 'Número de causas' : 'Número de causa'}
              htmlFor="parametro"
              ayuda={ayudaParametro}
              error={fieldErrors.parametro}
            >
              <Input
                {...a11yCampo('parametro', { ayuda: true, error: fieldErrors.parametro })}
                value={parametro}
                onChange={(e) => {
                  setParametro(e.target.value)
                  clearFieldError('parametro')
                }}
                inputMode={modo === 'lote' ? 'numeric' : undefined}
                maxLength={modo === 'lote' ? 3 : 60}
                disabled={loading}
                className={modo === 'solo' ? 'font-mono' : undefined}
              />
            </Field>
          )}
          <Field
            label="Trabajadores (1 a 4)"
            htmlFor="trabajadores"
            ayuda={esSolo ? 'Una sola causa se procesa con 1 trabajador.' : undefined}
            error={fieldErrors.trabajadores}
          >
            <Input
              {...a11yCampo('trabajadores', { ayuda: esSolo || undefined, error: fieldErrors.trabajadores })}
              type="number"
              min={1}
              max={4}
              value={trabajadoresEfectivos}
              onChange={(e) => {
                setTrabajadores(parseInt(e.target.value, 10) || 1)
                clearFieldError('trabajadores')
              }}
              disabled={loading || esSolo}
              className="max-w-24 tabular-nums"
            />
          </Field>
        </div>

        {modo !== 'solo' && (
          <Checkbox
            checked={continuar}
            onChange={(e) => setContinuar(e.target.checked)}
            disabled={loading}
            label="Omitir causas ya procesadas (continuar)"
          />
        )}
      </Seccion>

      <Seccion numero={4} titulo="Confirmar">
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <Dato termino="Archivo">{file ? file.name : 'Sin elegir'}</Dato>
          <Dato termino="Hoja">{hoja.trim() || 'Primera hoja'}</Dato>
          <Dato termino="Filtros">{resumenFiltros}</Dato>
          <Dato termino="Modo">
            {MODO_ETIQUETAS[modo]}
            {modo !== 'pendientes' && parametro.trim() ? ` · ${parametro.trim()}` : ''}
          </Dato>
          <Dato termino="Trabajadores">{trabajadoresEfectivos}</Dato>
          <Dato termino="Omitir procesadas">{continuarEfectivo ? 'Sí' : 'No'}</Dato>
        </dl>

        {error && (
          <Alert tono="peligro" rol="alert">
            {error}
          </Alert>
        )}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" cargando={loading}>
            {loading ? 'Creando lote…' : 'Crear lote'}
          </Button>
          <ButtonLink href="/lotes" variante="secundario">
            Cancelar
          </ButtonLink>
        </div>
      </Seccion>
    </form>
  )
}

function Seccion({ numero, titulo, children }: { numero: number; titulo: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-tarjeta bg-surface p-4 shadow-tarjeta sm:p-6">
      <legend className="sr-only">{`Paso ${numero}: ${titulo}`}</legend>
      <div aria-hidden="true" className="mb-4 flex items-center gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-on-primary">
          {numero}
        </span>
        <span className="text-base font-semibold text-fg">{titulo}</span>
      </div>
      <div className="space-y-4">{children}</div>
    </fieldset>
  )
}

function Dato({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{termino}</dt>
      <dd className="break-words font-medium text-fg">{children}</dd>
    </div>
  )
}
