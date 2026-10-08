'use client'

import { startTransition, useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/Button'
import { formatFecha } from '@/lib/fechas'

const INTERVALO_REFRESCO_MS = 45_000
const ESPERA_MAXIMA_MS = 60_000

export default function RefrescoInicio({ consultadoEn }: { consultadoEn: string }) {
  const router = useRouter()
  const [actualizando, setActualizando] = useState(false)
  const [anuncio, setAnuncio] = useState('')
  const enCurso = useRef(false)
  const manual = useRef(false)
  const ultimaSolicitud = useRef(0)
  const ultimaRespuesta = useRef(consultadoEn)
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refrescar = useCallback((solicitudManual: boolean) => {
    if (document.visibilityState !== 'visible' || enCurso.current) return
    enCurso.current = true
    manual.current = solicitudManual
    ultimaSolicitud.current = Date.now()
    setActualizando(true)
    if (solicitudManual) setAnuncio('Actualizando el resumen…')
    espera.current = setTimeout(() => {
      if (!enCurso.current) return
      enCurso.current = false
      setActualizando(false)
      if (manual.current) setAnuncio('No se pudo confirmar la actualización. Intenta de nuevo.')
      manual.current = false
      espera.current = null
    }, ESPERA_MAXIMA_MS)
    startTransition(() => router.refresh())
  }, [router])

  useEffect(() => {
    if (consultadoEn === ultimaRespuesta.current) return
    ultimaRespuesta.current = consultadoEn
    if (!enCurso.current) return
    enCurso.current = false
    if (espera.current) clearTimeout(espera.current)
    espera.current = null
    setActualizando(false)
    if (manual.current) setAnuncio('Resumen actualizado.')
    manual.current = false
  }, [consultadoEn])

  useEffect(() => {
    if (ultimaSolicitud.current === 0) ultimaSolicitud.current = Date.now()
    let temporizador: ReturnType<typeof setInterval> | undefined

    function detener() {
      if (temporizador) clearInterval(temporizador)
      temporizador = undefined
    }

    function alCambiarVisibilidad() {
      detener()
      if (document.visibilityState !== 'visible') return
      if (Date.now() - ultimaSolicitud.current >= INTERVALO_REFRESCO_MS) refrescar(false)
      temporizador = setInterval(() => refrescar(false), INTERVALO_REFRESCO_MS)
    }

    alCambiarVisibilidad()
    document.addEventListener('visibilitychange', alCambiarVisibilidad)
    return () => {
      detener()
      document.removeEventListener('visibilitychange', alCambiarVisibilidad)
      if (espera.current) clearTimeout(espera.current)
    }
  }, [refrescar])

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm text-muted">
      <p>
        Datos consultados: <time dateTime={consultadoEn} className="tabular-nums">{formatFecha(consultadoEn)}</time>
      </p>
      <Button variante="secundario" tamano="sm" cargando={actualizando} onClick={() => refrescar(true)}>
        {actualizando ? 'Actualizando…' : 'Actualizar ahora'}
      </Button>
      <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{anuncio}</span>
    </div>
  )
}
