'use client'

import { useEffect, useMemo, useState } from 'react'
import { Alert } from '@/components/ui/Alert'
import { cx } from '@/lib/cx'
import { createClient } from '@/lib/supabase/client'
import {
  describirHace,
  evaluarLatido,
  leerEstadoServidor,
  textoServidor,
  tonoServidor,
  type EstadoServidor,
} from '@/lib/servidor'
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

/**
 * Estado del servidor de procesamiento, en vivo. Consulta el último latido cada 10 s (solo con la
 * pestaña visible) y recalcula su antigüedad cada segundo: si el servicio deja de latir, el aviso
 * aparece sin esperar al refresco de la página. El punto con onda significa "vivo"; sin onda, no.
 */
export function PulsoServidor({ inicial }: { inicial: EstadoServidor }) {
  const supabase = useMemo(() => createClient(), [])
  const [ultimo, setUltimo] = useState(inicial)
  const [ahora, setAhora] = useState<number | null>(null)

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

  // Reloj de un segundo para "hace N s" y para detectar un latido vencido entre consultas.
  useEffect(() => {
    const tic = () => setAhora(Date.now())
    tic()
    const id = setInterval(tic, 1000)
    return () => clearInterval(id)
  }, [])

  const estado: EstadoServidor =
    ahora !== null && ultimo.tipo !== 'desconocido' && ultimo.latidoEn
      ? evaluarLatido(ultimo.latidoEn, ultimo.tipo === 'activo' && ultimo.procesando, ultimo.host ?? '', ahora)
      : ultimo

  if (estado.tipo === 'caido') {
    return (
      <div className="animate-subir">
        <Alert tono="peligro" rol="alert" titulo="El servidor de procesamiento no responde">
          Los lotes nuevos quedarán en &ldquo;Solicitada&rdquo; hasta que el servicio vuelva a estar activo
          {estado.host ? ` en ${estado.host}` : ''}. {textoServidor(estado)}.
        </Alert>
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
          {vivo ? <span className={cx('absolute inset-0 rounded-full animate-latido', PUNTO[tono])} /> : null}
          <span className={cx('relative size-2 rounded-full', PUNTO[tono])} />
        </span>
        {textoServidor(estado)}
      </span>
      {vivo ? (
        <span className="text-xs tabular-nums">
          {estado.host} · señal {describirHace(estado.hace)}
        </span>
      ) : null}
    </p>
  )
}
