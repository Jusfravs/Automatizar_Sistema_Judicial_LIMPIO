'use client'

import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { traducirErrorInterno } from '@/lib/lotes'
import {
  DECISIONES_REVISION,
  DECISION_ETIQUETAS,
  type DecisionRevision,
  type Etapa,
  type Fase,
} from '@/lib/casos'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Radio } from '@/components/ui/Radio'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'

const MAX_OBSERVACION = 1000
// Aviso que deja una revisión al saltar a la siguiente causa; lo muestra el formulario de destino.
const CLAVE_AVISO = 'revision:aviso'

type Campo = 'decision' | 'etapa' | 'fase' | 'observacion'

/** Lugar de esta causa en la cola de revisiones pendientes. */
export type ColaRevision = { posicion: number | null; total: number; siguiente: string | null }

interface RevisionFormProps {
  auditoriaId: number
  causa: string
  cola: ColaRevision | null
  permiteAceptarIA: boolean
  etapas: Etapa[]
  fases: Fase[]
}

/** Lee y borra el aviso; solo lo devuelve si iba dirigido a esta causa (si no, se descarta). */
function leerAviso(causa: string): string {
  try {
    const crudo = sessionStorage.getItem(CLAVE_AVISO)
    sessionStorage.removeItem(CLAVE_AVISO)
    if (!crudo) return ''
    const { texto, destino } = JSON.parse(crudo) as { texto?: unknown; destino?: unknown }
    return destino === causa && typeof texto === 'string' ? texto : ''
  } catch {
    return ''
  }
}

function guardarAviso(texto: string, destino: string) {
  try {
    sessionStorage.setItem(CLAVE_AVISO, JSON.stringify({ texto, destino }))
  } catch {
    // Sin almacenamiento (modo privado): se navega igual, solo sin el aviso.
  }
}

// Campos donde las teclas 1–4 se escriben, no eligen decisión.
const SELECTOR_CAMPO =
  'input:not([type="radio"]):not([type="checkbox"]):not([type="button"]):not([type="submit"]), textarea, select, [contenteditable="true"]'

/**
 * Revisión humana de la clasificación propuesta por la IA, pensada para revisar en serie:
 * muestra "3 de 12", permite "Guardar y siguiente" y tiene atajos. Las teclas 1–4 eligen la
 * decisión solo con el foco dentro del formulario y fuera de campos de texto (WCAG 2.1.4);
 * Ctrl+Enter guarda desde cualquier punto de la página.
 */
export default function RevisionForm({ auditoriaId, causa, cola, permiteAceptarIA, etapas, fases }: RevisionFormProps) {
  const router = useRouter()
  const id = useId()
  const formulario = useRef<HTMLFormElement>(null)
  const [decision, setDecision] = useState<DecisionRevision | ''>('')
  const [etapa, setEtapa] = useState('')
  const [fase, setFase] = useState('')
  const [observacion, setObservacion] = useState('')
  const [errores, setErrores] = useState<Partial<Record<Campo, string>>>({})
  const [errorGeneral, setErrorGeneral] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  // Aviso que deja la revisión anterior al usar "Guardar y siguiente": va en la fila del contador.
  const [avisoAnterior, setAvisoAnterior] = useState('')
  const [enviando, setEnviando] = useState<false | 'guardar' | 'siguiente'>(false)
  const siguienteRef = useRef(false)

  const corrigiendo = decision === 'CORREGIR_MANUALMENTE'
  const fasesDeEtapa = etapa ? fases.filter((f) => f.eta_id === Number(etapa)) : []
  const haySiguiente = Boolean(cola?.siguiente)

  function enfocarPrimeraDecision() {
    document.querySelector<HTMLInputElement>(`input[name="${id}-decision"]:not(:disabled)`)?.focus()
  }

  // Aviso de la revisión anterior (viene de "Guardar y siguiente"). Se lee tras montar: el servidor
  // no tiene sessionStorage. Leerlo dentro del temporizador evita perderlo con el doble montaje de
  // desarrollo. Al llegar desde la revisión anterior, el foco va a la primera decisión.
  useEffect(() => {
    const t = setTimeout(() => {
      const aviso = leerAviso(causa)
      if (!aviso) return
      setAvisoAnterior(aviso)
      enfocarPrimeraDecision()
    }, 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al montar
  }, [])

  // Ctrl+Enter: guardar desde cualquier punto de la página (lleva modificador, no choca con 2.1.4).
  useEffect(() => {
    function alTeclear(e: globalThis.KeyboardEvent) {
      if (enviando || e.key !== 'Enter' || !(e.ctrlKey || e.metaKey)) return
      if (e.target instanceof HTMLElement && e.target.closest('dialog[open]')) return
      e.preventDefault()
      siguienteRef.current = haySiguiente
      formulario.current?.requestSubmit()
    }
    document.addEventListener('keydown', alTeclear)
    return () => document.removeEventListener('keydown', alTeclear)
  }, [enviando, haySiguiente])

  // 1–4: solo con el foco dentro del formulario y fuera de campos de texto.
  function alTeclearFormulario(e: KeyboardEvent<HTMLFormElement>) {
    if (enviando || e.ctrlKey || e.metaKey || e.altKey) return
    if (e.target instanceof HTMLElement && e.target.closest(SELECTOR_CAMPO)) return
    const n = Number(e.key)
    if (!Number.isInteger(n) || n < 1 || n > DECISIONES_REVISION.length) return
    const d = DECISIONES_REVISION[n - 1]
    if (d === 'ACEPTAR_IA' && !permiteAceptarIA) return
    e.preventDefault()
    setDecision(d)
    setErrores((prev) => ({ ...prev, decision: undefined }))
    document.querySelector<HTMLInputElement>(`input[name="${id}-decision"][value="${d}"]`)?.focus()
  }

  function validar(): Partial<Record<Campo, string>> {
    const e: Partial<Record<Campo, string>> = {}
    if (!decision) e.decision = 'Selecciona una decisión'
    else if (decision === 'ACEPTAR_IA' && !permiteAceptarIA) e.decision = 'La IA no propuso un cambio que se pueda aceptar'
    if (corrigiendo) {
      if (!etapa) e.etapa = 'Selecciona la etapa'
      if (!fase) e.fase = 'Selecciona la fase'
      else if (!fasesDeEtapa.some((f) => f.fas_id === Number(fase))) e.fase = 'La fase no pertenece a la etapa elegida'
      const texto = observacion.trim()
      if (!texto) e.observacion = 'La observación es obligatoria al corregir manualmente'
      else if (texto.length > MAX_OBSERVACION) e.observacion = `Máximo ${MAX_OBSERVACION} caracteres`
    }
    return e
  }

  function enfocarPrimerError(e: Partial<Record<Campo, string>>) {
    const primero = (['decision', 'etapa', 'fase', 'observacion'] as Campo[]).find((c) => e[c])
    if (!primero) return
    const destino = primero === 'decision'
      ? document.querySelector<HTMLInputElement>(`input[name="${id}-decision"]:not(:disabled)`)
      : document.getElementById(`${id}-${primero}`)
    destino?.focus()
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    // El botón pulsado decide si se pasa a la siguiente; Ctrl+Enter lo indica por referencia.
    const emisor = (evento.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
    const irASiguiente = (emisor ? emisor.value === 'siguiente' : siguienteRef.current) && haySiguiente
    siguienteRef.current = false

    setErrorGeneral('')
    setConfirmacion('')
    const e = validar()
    setErrores(e)
    if (Object.keys(e).length > 0) {
      enfocarPrimerError(e)
      return
    }

    setEnviando(irASiguiente ? 'siguiente' : 'guardar')
    const supabase = createClient()
    const { data, error } = await supabase.rpc('registrar_revision', {
      p_auditoria_id: auditoriaId,
      p_decision: decision,
      ...(corrigiendo
        ? { p_eta_id: Number(etapa), p_fas_id: Number(fase), p_observacion: observacion.trim() }
        : {}),
    })
    if (error) {
      setEnviando(false)
      console.error('No se pudo registrar la revisión:', error.message)
      setErrorGeneral(traducirErrorInterno(error.message))
      return
    }

    const pospuesta = data === 'PENDIENTE'
    if (irASiguiente && cola?.siguiente) {
      guardarAviso(`${pospuesta ? 'Pospuesta' : 'Registrada'}: ${causa}`, cola.siguiente)
      router.push(`/casos/${encodeURIComponent(cola.siguiente)}`)
      return
    }
    setEnviando(false)
    setConfirmacion(pospuesta ? 'La revisión quedó pospuesta.' : 'Revisión registrada correctamente.')
    setDecision('')
    setEtapa('')
    setFase('')
    setObservacion('')
    // El botón pulsado puede desaparecer al refrescar: el foco vuelve a la primera decisión.
    enfocarPrimeraDecision()
    router.refresh()
  }

  const ocupado = enviando !== false

  return (
    <div className="space-y-4">
      {cola && cola.total > 0 ? (
        <div className="flex min-h-5 flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-muted">
          {/* Aviso de la revisión anterior en la misma fila: no desplaza el formulario. */}
          <span role="status" className="w-full font-medium text-exito-fg empty:hidden">
            {avisoAnterior ? `✓ ${avisoAnterior}. Esta es la siguiente pendiente.` : ''}
          </span>
          <span className="tabular-nums">
            {cola.posicion ? (
              <>
                Revisión <span className="font-semibold text-fg">{cola.posicion}</span> de {cola.total}{' '}
                {cola.total === 1 ? 'pendiente' : 'pendientes'}
              </>
            ) : (
              <>{cola.total === 1 ? '1 pendiente' : `${cola.total} pendientes`}</>
            )}
          </span>
          {cola.total > 1 ? (
            <span className="h-1 w-20 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
              <span
                className="block h-full origin-left rounded-full bg-atencion-solid transition-transform duration-(--duracion-lenta) ease-salida"
                style={{ transform: `scaleX(${(cola.posicion ?? 0) / cola.total})` }}
              />
            </span>
          ) : null}
        </div>
      ) : null}

      <div role="status">
        {confirmacion ? <Alert tono="exito">{confirmacion}</Alert> : null}
      </div>
      <form ref={formulario} onSubmit={enviar} onKeyDown={alTeclearFormulario} className="space-y-4" noValidate>
        {errorGeneral && (
          <div className="animate-subir">
            <Alert tono="peligro" rol="alert">
              {errorGeneral}
            </Alert>
          </div>
        )}

        <fieldset aria-describedby={errores.decision ? `${id}-decision-error` : undefined}>
          <legend className="mb-2 text-sm font-medium text-muted">Decisión</legend>
          <div className="flex flex-col">
            {DECISIONES_REVISION.map((d, i) => {
              const deshabilitada = d === 'ACEPTAR_IA' && !permiteAceptarIA
              return (
                <Radio
                  key={d}
                  name={`${id}-decision`}
                  value={d}
                  checked={decision === d}
                  disabled={ocupado || deshabilitada}
                  aria-keyshortcuts={deshabilitada ? undefined : String(i + 1)}
                  onChange={() => {
                    setDecision(d)
                    setErrores((prev) => ({ ...prev, decision: undefined }))
                  }}
                  label={
                    <span className="flex w-full items-baseline gap-2">
                      <span className="flex-1">
                        {DECISION_ETIQUETAS[d]}
                        {deshabilitada && ' (no disponible: la IA no propuso un cambio con evidencias)'}
                      </span>
                      {deshabilitada ? null : (
                        <kbd aria-hidden="true" className="hidden rounded-sm border border-subtle px-1.5 font-sans text-rotulo text-muted sm:inline">
                          {i + 1}
                        </kbd>
                      )}
                    </span>
                  }
                />
              )
            })}
          </div>
          {errores.decision && <p id={`${id}-decision-error`} className="mt-1 text-sm font-medium text-peligro-fg">{errores.decision}</p>}
        </fieldset>

        {corrigiendo && (
          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold text-fg">Corrección manual</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor={`${id}-etapa`} className="mb-1.5 block text-sm font-medium text-muted">Etapa</label>
                <Select
                  id={`${id}-etapa`}
                  value={etapa}
                  disabled={ocupado}
                  aria-invalid={!!errores.etapa}
                  aria-describedby={errores.etapa ? `${id}-etapa-error` : undefined}
                  onChange={(e) => {
                    setEtapa(e.target.value)
                    setFase('')
                    setErrores((prev) => ({ ...prev, etapa: undefined, fase: undefined }))
                  }}
                >
                  <option value="">Selecciona una etapa</option>
                  {etapas.map((e) => <option key={e.eta_id} value={e.eta_id}>{e.nombre}</option>)}
                </Select>
                {errores.etapa && <p id={`${id}-etapa-error`} className="mt-1 text-sm font-medium text-peligro-fg">{errores.etapa}</p>}
              </div>
              <div>
                <label htmlFor={`${id}-fase`} className="mb-1.5 block text-sm font-medium text-muted">Fase</label>
                <Select
                  id={`${id}-fase`}
                  value={fase}
                  disabled={ocupado || !etapa}
                  aria-invalid={!!errores.fase}
                  aria-describedby={errores.fase ? `${id}-fase-error` : undefined}
                  onChange={(e) => {
                    setFase(e.target.value)
                    setErrores((prev) => ({ ...prev, fase: undefined }))
                  }}
                >
                  <option value="">{etapa ? 'Selecciona una fase' : 'Elige primero la etapa'}</option>
                  {fasesDeEtapa.map((f) => <option key={f.fas_id} value={f.fas_id}>{f.nombre}</option>)}
                </Select>
                {errores.fase && <p id={`${id}-fase-error`} className="mt-1 text-sm font-medium text-peligro-fg">{errores.fase}</p>}
              </div>
            </div>
            <div>
              <label htmlFor={`${id}-observacion`} className="mb-1.5 block text-sm font-medium text-muted">
                Observación (obligatoria, máximo {MAX_OBSERVACION} caracteres)
              </label>
              <Textarea
                id={`${id}-observacion`}
                value={observacion}
                maxLength={MAX_OBSERVACION}
                rows={4}
                disabled={ocupado}
                aria-invalid={!!errores.observacion}
                aria-describedby={[errores.observacion ? `${id}-observacion-error` : '', `${id}-contador`].filter(Boolean).join(' ')}
                onChange={(e) => {
                  setObservacion(e.target.value)
                  setErrores((prev) => ({ ...prev, observacion: undefined }))
                }}
              />
              {errores.observacion && <p id={`${id}-observacion-error`} className="mt-1 text-sm font-medium text-peligro-fg">{errores.observacion}</p>}
              <p id={`${id}-contador`} className="mt-1 text-right text-xs tabular-nums text-muted">{observacion.length}/{MAX_OBSERVACION}</p>
            </div>
          </fieldset>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {haySiguiente ? (
            <>
              <Button type="submit" value="siguiente" cargando={enviando === 'siguiente'} disabled={ocupado} aria-keyshortcuts="Control+Enter">
                Guardar y siguiente
              </Button>
              <Button type="submit" value="guardar" variante="secundario" cargando={enviando === 'guardar'} disabled={ocupado}>
                Solo guardar
              </Button>
            </>
          ) : (
            <Button type="submit" value="guardar" cargando={enviando === 'guardar'} disabled={ocupado} aria-keyshortcuts="Control+Enter">
              Registrar revisión
            </Button>
          )}
        </div>
        <p className="hidden text-xs text-muted sm:block">
          Atajos: <kbd className="font-sans font-semibold text-fg">1</kbd>–<kbd className="font-sans font-semibold text-fg">4</kbd> eligen la
          decisión · <kbd className="font-sans font-semibold text-fg">Ctrl</kbd> + <kbd className="font-sans font-semibold text-fg">Enter</kbd>{' '}
          {haySiguiente ? 'guarda y pasa a la siguiente' : 'registra la revisión'}
        </p>
      </form>
    </div>
  )
}
