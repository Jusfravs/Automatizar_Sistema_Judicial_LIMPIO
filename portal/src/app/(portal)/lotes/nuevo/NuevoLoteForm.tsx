'use client'

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { XLSX_MIME, MAX_FILE_SIZE, MAX_ARCHIVO_NOMBRE, MAX_HOJA, FILTROS_DEFAULTS, MODO_ETIQUETAS, traducirErrorInterno } from '@/lib/lotes'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { Checkbox } from '@/components/ui/Checkbox'
import { Field, a11yCampo } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { ZonaArchivo } from '@/components/ui/ZonaArchivo'
import { FOCO } from '@/components/ui/estilos'
import { cx } from '@/lib/cx'

type Modo = 'solo' | 'lote' | 'pendientes'
type Filtros = {
  sucursal: string
  oficina: string
  estado_judicial: string
}

type CampoConError = keyof Filtros | 'file' | 'hoja' | 'parametro' | 'trabajadores'
const ORDEN_CAMPOS: CampoConError[] = ['file', 'hoja', 'sucursal', 'parametro', 'trabajadores']
const MODOS: readonly Modo[] = ['lote', 'solo', 'pendientes']

const DESCRIPCION_MODO: Record<Modo, string> = {
  lote: 'Las primeras N causas pendientes del Excel (de 2 a 100).',
  solo: 'Una causa concreta, por su número.',
  pendientes: 'Todas las causas pendientes del Excel. Puede tardar horas.',
}

const PASOS = [
  { corto: 'Archivo', titulo: 'Archivo Excel', descripcion: 'Sube el Excel con las causas que quieres consultar.' },
  { corto: 'Filtros', titulo: 'Filtros', descripcion: 'Qué causas del Excel entran en el lote.' },
  { corto: 'Modo', titulo: 'Modo de ejecución', descripcion: 'Cuántas causas consultar y con cuántos trabajadores.' },
  { corto: 'Confirmar', titulo: 'Confirmar', descripcion: 'Revisa el resumen antes de crear el lote. Puedes editar cualquier paso.' },
] as const

// Campos que valida cada paso al pulsar "Siguiente".
const CAMPOS_POR_PASO: Record<number, CampoConError[]> = {
  1: ['file', 'hoja'],
  2: ['sucursal'],
  3: ['parametro', 'trabajadores'],
  4: [],
}

function pasoDeCampo(campo: CampoConError): number {
  return Number(Object.entries(CAMPOS_POR_PASO).find(([, campos]) => campos.includes(campo))?.[0] ?? 1)
}

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
  // Asistente: paso visible y pasos ya validados (se puede volver a ellos desde el indicador).
  const [paso, setPaso] = useState(1)
  const [completados, setCompletados] = useState<Set<number>>(() => new Set())
  const tituloPaso = useRef<HTMLHeadingElement>(null)
  const primerRender = useRef(true)

  // Al cambiar de paso, el foco va al título del panel (no en la carga inicial).
  useEffect(() => {
    if (primerRender.current) {
      primerRender.current = false
      return
    }
    tituloPaso.current?.focus()
  }, [paso])

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

  const validarArchivo = (f: File) => validateField('file', f) ?? validateField('archivo_nombre', f.name)

  // Validación en línea al salir de un campo: el error aparece antes de llegar al final.
  const validarAlSalir = (campo: CampoConError, valor: string) => {
    const mensaje = validateField(campo, valor)
    setFieldErrors((prev) => ({ ...prev, [campo]: mensaje }))
  }

  const irAPaso = (destino: number) => {
    setError('')
    setPaso(destino)
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
    if (ruta.startsWith('b2:')) {
      const id = ruta.split('/').at(-1)?.replace(/\.xlsx$/, '')
      try {
        const respuesta = await fetch('/api/lotes/archivo', {
          method: 'DELETE', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id }),
        })
        if (!respuesta.ok) console.warn('No se pudo limpiar el archivo huérfano de B2:', respuesta.status)
      } catch {
        console.warn('No se pudo limpiar el archivo huérfano de B2')
      }
      return
    }
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

    // Pasos 1 a 3: "Siguiente" valida solo los campos del paso visible.
    if (paso < PASOS.length) {
      const delPaso = CAMPOS_POR_PASO[paso].filter((campo) => errores[campo])
      setFieldErrors((prev) => {
        const next = { ...prev }
        for (const campo of CAMPOS_POR_PASO[paso]) next[campo] = errores[campo]
        return next
      })
      if (delPaso.length > 0) {
        document.getElementById(delPaso[0])?.focus()
        return
      }
      setCompletados((prev) => new Set(prev).add(paso))
      setPaso(paso + 1)
      return
    }

    // Paso final: si algo quedó inválido, se vuelve al paso que lo contiene.
    setFieldErrors(errores)
    const primerCampo = ORDEN_CAMPOS.find((campo) => errores[campo])
    if (primerCampo) {
      setError('Revisa los campos marcados')
      setPaso(pasoDeCampo(primerCampo))
      return
    }

    setLoading(true)
    const supabase = createClient()
    const id = crypto.randomUUID()
    let archivoRuta = `entradas/${id}.xlsx`
    let archivoSubido = false

    try {
      if (process.env.NEXT_PUBLIC_LOTE_STORAGE === 'b2') {
        const firma = await fetch('/api/lotes/archivo', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id, size: file!.size }),
        })
        if (!firma.ok) throw new Error(`B2_FIRMA_HTTP_${firma.status}`)
        const { url, ruta } = await firma.json() as { url: string; ruta: string }
        if (!url || !ruta?.startsWith('b2:')) throw new Error('B2_FIRMA_INVALIDA')
        archivoRuta = ruta
        archivoSubido = true
        const subida = await fetch(url, {
          method: 'PUT', headers: { 'Content-Type': XLSX_MIME }, body: file,
        })
        if (!subida.ok) throw new Error(`B2_SUBIDA_HTTP_${subida.status}`)
      } else {
        const { error: uploadError } = await supabase.storage
          .from('lotes')
          .upload(archivoRuta, file!, { contentType: XLSX_MIME, upsert: false })
        if (uploadError) {
          console.error('No se pudo subir el archivo:', uploadError.message)
          setError(traducirErrorInterno(uploadError.message))
          setLoading(false)
          return
        }
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

  return (
    <form onSubmit={handleSubmit} className="max-w-3xl space-y-6" noValidate>
      <IndicadorPasos actual={paso} completados={completados} alElegir={irAPaso} deshabilitado={loading} />

      <div className="rounded-tarjeta bg-surface p-4 shadow-tarjeta sm:p-6">
        {/* Panel del paso: el título recibe el foco al cambiar, así el lector anuncia dónde está. */}
        <div key={paso} className="animate-aparecer space-y-5">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted">
              Paso {paso} de {PASOS.length}
            </p>
            <h2 ref={tituloPaso} tabIndex={-1} className="text-lg font-semibold text-fg outline-none">
              {PASOS[paso - 1].titulo}
            </h2>
            <p className="text-sm text-muted text-pretty">{PASOS[paso - 1].descripcion}</p>
          </div>

          {paso === 1 && (
            <div className="space-y-4">
              <Field label="Archivo .xlsx" htmlFor="file" error={fieldErrors.file}>
                <ZonaArchivo
                  {...a11yCampo('file', { error: fieldErrors.file })}
                  archivo={file}
                  alCambiar={(f) => {
                    setFile(f)
                    setFieldErrors((prev) => ({ ...prev, file: f ? validarArchivo(f) : undefined }))
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
            </div>
          )}

          {paso === 2 && (
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Sucursal" htmlFor="sucursal" error={fieldErrors.sucursal}>
                <Input
                  {...a11yCampo('sucursal', { error: fieldErrors.sucursal })}
                  value={filtros.sucursal}
                  onChange={(e) => {
                    setFiltros({ ...filtros, sucursal: e.target.value })
                    clearFieldError('sucursal')
                  }}
                  onBlur={() => validarAlSalir('sucursal', filtros.sucursal)}
                  disabled={loading}
                />
              </Field>
              <Field label="Oficina" htmlFor="oficina" ayuda="Vacía = todas.">
                <Input
                  {...a11yCampo('oficina', { ayuda: true })}
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
          )}

          {paso === 3 && (
            <div className="space-y-5">
              <fieldset>
                <legend className="mb-2 text-sm font-medium text-muted">Qué causas consultar</legend>
                <div className="grid gap-3 sm:grid-cols-3">
                  {MODOS.map((m) => (
                    <label
                      key={m}
                      className={cx(
                        'flex cursor-pointer flex-col gap-1 rounded-control border p-3 transition-colors',
                        'has-[:checked]:border-primary has-[:checked]:bg-surface-2',
                        'border-strong hover:bg-surface-2 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus',
                        loading && 'cursor-not-allowed opacity-70',
                      )}
                    >
                      <span className="flex items-center gap-2 text-sm font-semibold text-fg">
                        <input
                          type="radio"
                          name="modo"
                          value={m}
                          checked={modo === m}
                          onChange={() => {
                            setModo(m)
                            clearFieldError('parametro')
                          }}
                          disabled={loading}
                          className="size-4 shrink-0 accent-primary"
                        />
                        {MODO_ETIQUETAS[m]}
                      </span>
                      <span className="text-xs text-muted text-pretty">{DESCRIPCION_MODO[m]}</span>
                    </label>
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
                      onBlur={() => validarAlSalir('parametro', parametro)}
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
                  ayuda={esSolo ? 'Una sola causa se procesa con 1 trabajador.' : 'Más trabajadores terminan antes.'}
                  error={fieldErrors.trabajadores}
                >
                  <Input
                    {...a11yCampo('trabajadores', { ayuda: true, error: fieldErrors.trabajadores })}
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
            </div>
          )}

          {paso === 4 && (
            <dl className="divide-y divide-subtle rounded-control border border-subtle text-sm">
              <FilaResumen termino="Archivo" alEditar={() => irAPaso(1)} deshabilitado={loading}>
                {file ? file.name : 'Sin elegir'}
                <span className="block text-xs font-normal text-muted">Hoja: {hoja.trim() || 'primera hoja'}</span>
              </FilaResumen>
              <FilaResumen termino="Filtros" alEditar={() => irAPaso(2)} deshabilitado={loading}>
                Sucursal: {filtros.sucursal.trim() || '—'} · Oficina: {filtros.oficina.trim() || 'todas'} · Estado judicial:{' '}
                {filtros.estado_judicial.trim() || '—'}
              </FilaResumen>
              <FilaResumen termino="Modo" alEditar={() => irAPaso(3)} deshabilitado={loading}>
                {MODO_ETIQUETAS[modo]}
                {modo !== 'pendientes' && parametro.trim() ? ` · ${parametro.trim()}` : ''}
                <span className="block text-xs font-normal text-muted">
                  {trabajadoresEfectivos} {trabajadoresEfectivos === 1 ? 'trabajador' : 'trabajadores'} · Omitir procesadas:{' '}
                  {continuarEfectivo ? 'sí' : 'no'}
                </span>
              </FilaResumen>
            </dl>
          )}

          <div role="status">
            {error ? (
              <Alert tono="peligro" rol="alert">
                {error}
              </Alert>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-subtle pt-5">
            {paso < PASOS.length ? (
              <Button type="submit" disabled={loading}>
                Siguiente
              </Button>
            ) : (
              <Button type="submit" cargando={loading}>
                {loading ? 'Creando lote…' : 'Crear lote'}
              </Button>
            )}
            {paso > 1 ? (
              <Button variante="secundario" onClick={() => irAPaso(paso - 1)} disabled={loading}>
                Atrás
              </Button>
            ) : null}
            <ButtonLink href="/lotes" variante="fantasma" className="sm:ml-auto">
              Cancelar
            </ButtonLink>
          </div>
        </div>
      </div>
    </form>
  )
}

/**
 * Indicador de pasos. Los pasos ya completados se pueden pulsar para volver; los siguientes no
 * (se llega a ellos validando con "Siguiente"). El paso actual lleva aria-current="step".
 */
function IndicadorPasos({
  actual,
  completados,
  alElegir,
  deshabilitado,
}: {
  actual: number
  completados: Set<number>
  alElegir: (paso: number) => void
  deshabilitado: boolean
}) {
  return (
    <nav aria-label="Pasos para crear el lote">
      <ol className="grid grid-cols-4 gap-2">
        {PASOS.map((p, i) => {
          const numero = i + 1
          const esActual = numero === actual
          const hecho = completados.has(numero) && !esActual
          const accesible = (hecho || numero < actual) && !deshabilitado
          const contenido = (
            <>
              <span
                className={cx(
                  'h-1 w-full rounded-full transition-colors duration-(--duracion-lenta)',
                  esActual ? 'bg-primary' : hecho || numero < actual ? 'bg-exito-solid' : 'bg-surface-2',
                )}
              />
              <span className="flex items-center gap-1.5 text-xs font-medium">
                <span className={cx('tabular-nums', esActual ? 'text-primary' : 'text-muted')}>{numero}.</span>
                <span className={cx('truncate', esActual ? 'font-semibold text-fg' : 'text-muted')}>{p.corto}</span>
                {hecho ? <span className="sr-only">(completado)</span> : null}
              </span>
            </>
          )
          return (
            <li key={p.corto} aria-current={esActual ? 'step' : undefined}>
              {accesible ? (
                <button
                  type="button"
                  onClick={() => alElegir(numero)}
                  className={cx('flex w-full flex-col items-start gap-2 rounded-sm text-left hover:opacity-80', FOCO)}
                >
                  {contenido}
                </button>
              ) : (
                <div className="flex flex-col items-start gap-2">{contenido}</div>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function FilaResumen({
  termino,
  children,
  alEditar,
  deshabilitado,
}: {
  termino: string
  children: ReactNode
  alEditar: () => void
  deshabilitado: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="min-w-0">
        <dt className="text-muted">{termino}</dt>
        <dd className="mt-0.5 font-medium text-fg [overflow-wrap:anywhere]">{children}</dd>
      </div>
      <Button variante="fantasma" tamano="sm" onClick={alEditar} disabled={deshabilitado} aria-label={`Editar ${termino.toLowerCase()}`}>
        Editar
      </Button>
    </div>
  )
}
