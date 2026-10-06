'use client'

import { useId, useState, type FormEvent } from 'react'
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
type Campo = 'decision' | 'etapa' | 'fase' | 'observacion'

interface RevisionFormProps {
  auditoriaId: number
  permiteAceptarIA: boolean
  etapas: Etapa[]
  fases: Fase[]
}

export default function RevisionForm({ auditoriaId, permiteAceptarIA, etapas, fases }: RevisionFormProps) {
  const router = useRouter()
  const id = useId()
  const [decision, setDecision] = useState<DecisionRevision | ''>('')
  const [etapa, setEtapa] = useState('')
  const [fase, setFase] = useState('')
  const [observacion, setObservacion] = useState('')
  const [errores, setErrores] = useState<Partial<Record<Campo, string>>>({})
  const [errorGeneral, setErrorGeneral] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [enviando, setEnviando] = useState(false)

  const corrigiendo = decision === 'CORREGIR_MANUALMENTE'
  const fasesDeEtapa = etapa ? fases.filter((f) => f.eta_id === Number(etapa)) : []

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

  async function enviar(evento: FormEvent) {
    evento.preventDefault()
    setErrorGeneral('')
    setConfirmacion('')
    const e = validar()
    setErrores(e)
    if (Object.keys(e).length > 0) {
      enfocarPrimerError(e)
      return
    }

    setEnviando(true)
    const supabase = createClient()
    const { data, error } = await supabase.rpc('registrar_revision', {
      p_auditoria_id: auditoriaId,
      p_decision: decision,
      ...(corrigiendo
        ? { p_eta_id: Number(etapa), p_fas_id: Number(fase), p_observacion: observacion.trim() }
        : {}),
    })
    setEnviando(false)
    if (error) {
      console.error('No se pudo registrar la revisión:', error.message)
      setErrorGeneral(traducirErrorInterno(error.message))
      return
    }
    setConfirmacion(data === 'PENDIENTE' ? 'La revisión quedó pospuesta.' : 'Revisión registrada correctamente.')
    setDecision('')
    setEtapa('')
    setFase('')
    setObservacion('')
    router.refresh()
  }

  return (
    <div className="space-y-4">
      {confirmacion && (
        <Alert tono="exito" rol="status">
          {confirmacion}
        </Alert>
      )}
      <form onSubmit={enviar} className="space-y-4" noValidate>
        {errorGeneral && (
          <Alert tono="peligro" rol="alert">
            {errorGeneral}
          </Alert>
        )}

        <fieldset aria-describedby={errores.decision ? `${id}-decision-error` : undefined}>
          <legend className="mb-2 text-sm font-medium text-muted">Decisión</legend>
          <div className="flex flex-col">
            {DECISIONES_REVISION.map((d) => {
              const deshabilitada = d === 'ACEPTAR_IA' && !permiteAceptarIA
              return (
                <Radio
                  key={d}
                  name={`${id}-decision`}
                  value={d}
                  checked={decision === d}
                  disabled={enviando || deshabilitada}
                  onChange={() => {
                    setDecision(d)
                    setErrores((prev) => ({ ...prev, decision: undefined }))
                  }}
                  label={
                    <>
                      {DECISION_ETIQUETAS[d]}
                      {deshabilitada && ' (no disponible: la IA no propuso un cambio con evidencias)'}
                    </>
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
                  disabled={enviando}
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
                  disabled={enviando || !etapa}
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
                disabled={enviando}
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

        <Button type="submit" cargando={enviando}>
          {enviando ? 'Registrando…' : 'Registrar revisión'}
        </Button>
      </form>
    </div>
  )
}
