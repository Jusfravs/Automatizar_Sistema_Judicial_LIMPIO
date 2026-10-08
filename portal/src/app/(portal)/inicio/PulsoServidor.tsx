'use client'

import { useEffect, useMemo, useState } from 'react'
import { Alert } from '@/components/ui/Alert'
import { cx } from '@/lib/cx'
import { createClient } from '@/lib/supabase/client'
import { evaluarLatido, leerEstadoServidor, tonoServidor, type EstadoServidor } from '@/lib/servidor'
import type { Tono } from '@/lib/tonos'

// El servicio late cada 10 s: consultar más seguido no aporta nada.
const INTERVALO_CONSULTA_MS = 10_000

const PUNTO: Record<Tono, string> = {
  neutral: 'bg-neutral-solid',
  info: 'bg-info-solid',
  progreso: 'bg-progreso-solid',
  exito: 'bg-exito-solid',
  peligro: 'bg-peligro-solid',
  atencion: 'bg-atencion-solid',
}

const PILDORA: Record<Tono, string> = {
  neutral: 'bg-neutral-soft text-neutral-fg',
  info: 'bg-info-soft text-info-fg',
  progreso: 'bg-progreso-soft text-progreso-fg',
  exito: 'bg-exito-soft text-exito-fg',
  peligro: 'bg-peligro-soft text-peligro-fg',
  atencion: 'bg-atencion-soft text-atencion-fg',
}

/** Antigüedad en tramos de 10 s: el texto cambia poco y no distrae (WCAG 2.2.2). */
function antiguedad(ms: number | null): string {
  if (ms === null) return 'sin registro'
  const s = Math.floor(ms / 1000)
  if (s < 10) return 'hace menos de 10 s'
  if (s < 60) return `hace ${Math.floor(s / 10) * 10} s`
  const m = Math.floor(s / 60)
  if (m < 60) return m === 1 ? 'hace 1 min' : `hace ${m} min`
  const h = Math.floor(m / 60)
  if (h < 48) return h === 1 ? 'hace 1 h' : `hace ${h} h`
  return `hace ${Math.floor(h / 24)} días`
}

function etiqueta(estado: EstadoServidor): string {
  if (estado.tipo === 'activo') return estado.procesando ? 'Procesando un lote' : 'Activo, esperando lotes'
  if (estado.tipo === 'caido') return 'Sin conexión'
  return 'Estado desconocido'
}

/**
 * Estado del servidor de procesamiento, en vivo. Consulta el último latido cada 10 s (solo con la
 * pestaña visible) y recalcula su antigüedad cada segundo: si el servicio deja de latir, el aviso
 * aparece sin esperar al refresco de la página. Una onda sale del punto con cada latido recibido.
 *
 * El reloj se corrige con la hora del servidor (`instanteServidor`, del render en Vercel): un PC con
 * la hora adelantada no debe anunciar una caída que no existe.
 */
export function PulsoServidor({ inicial, instanteServidor }: { inicial: EstadoServidor; instanteServidor: number }) {
  const supabase = useMemo(() => createClient(), [])
  const [ultimo, setUltimo] = useState(inicial)
  const [ahora, setAhora] = useState<number | null>(null)
  const [desfase, setDesfase] = useState(0)

  // Consulta periódica del latido.
  useEffect(() => {
    let temporizador: ReturnType<typeof setInterval> | undefined
    let vigente = true

    async function consultar() {
      const estado = await leerEstadoServidor(supabase, Date.now())
      if (vigente && estado.tipo !== 'desconocido') setUltimo(estado)
    }
    function alCambiarVisibilidad() {
      if (temporizador) clearInterval(temporizador)
      temporizador = undefined
      if (document.visibilityState !== 'visible') return
      void consultar()
      temporizador = setInterval(consultar, INTERVALO_CONSULTA_MS)
    }

    alCambiarVisibilidad()
    document.addEventListener('visibilitychange', alCambiarVisibilidad)
    return () => {
      vigente = false
      if (temporizador) clearInterval(temporizador)
      document.removeEventListener('visibilitychange', alCambiarVisibilidad)
    }
  }, [supabase])

  // Reloj de un segundo, corregido con el desfase respecto al servidor.
  useEffect(() => {
    const correccion = Date.now() - instanteServidor
    const tic = () => {
      setDesfase(correccion)
      setAhora(Date.now())
    }
    const primero = setTimeout(tic, 0)
    const id = setInterval(tic, 1000)
    return () => {
      clearTimeout(primero)
      clearInterval(id)
    }
  }, [instanteServidor])

  const estado: EstadoServidor =
    ahora !== null && ultimo.tipo !== 'desconocido' && ultimo.latidoEn
      ? evaluarLatido(ultimo.latidoEn, ultimo.tipo === 'activo' && ultimo.procesando, ultimo.host ?? '', ahora - desfase)
      : ultimo

  if (estado.tipo === 'caido') {
    return (
      <div className="space-y-1">
        {/* El aviso tiene texto fijo: un role="alert" que cambia se relee entero cada vez. */}
        <Alert tono="peligro" rol="alert" titulo="El servidor de procesamiento no responde">
          Los lotes nuevos quedarán en &ldquo;Solicitada&rdquo; hasta que el servicio vuelva a estar activo
          {estado.host ? ` en ${estado.host}` : ''}.
        </Alert>
        <p className="text-xs tabular-nums text-muted">Última señal: {antiguedad(estado.hace)}</p>
      </div>
    )
  }

  const tono = tonoServidor(estado)
  const vivo = estado.tipo === 'activo'
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
      Servidor de procesamiento:
      <span className={cx('inline-flex items-center gap-2 rounded-full px-2.5 py-0.5 text-xs font-medium', PILDORA[tono])}>
        <span aria-hidden="true" className="relative flex size-2">
          {/* key = latido: la onda se reinicia (una sola vez) con cada señal real del servicio. */}
          {vivo ? <span key={estado.latidoEn} className={cx('absolute inset-0 rounded-full animate-latido', PUNTO[tono])} /> : null}
          <span className={cx('relative size-2 rounded-full', PUNTO[tono])} />
        </span>
        {etiqueta(estado)}
      </span>
      {vivo ? (
        <span className="text-xs tabular-nums">
          {estado.host} · señal {antiguedad(estado.hace)}
        </span>
      ) : null}
    </p>
  )
}
