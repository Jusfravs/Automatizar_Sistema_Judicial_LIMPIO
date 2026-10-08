'use client'

import { useEffect, useRef, useState } from 'react'

export type NumeroAnimadoProps = {
  valor: number
  /** Formato visible; por defecto separador de miles es-EC. */
  formato?: (n: number) => string
  /** Duración máxima del conteo (ms); nunca supera 400. */
  duracion?: number
  className?: string
}

const formatoBase = (n: number) => Math.round(n).toLocaleString('es-EC')
const DURACION_MAXIMA_MS = 400

// Sale rápido y se asienta: el ojo lee el valor final antes de que termine.
const salidaCubica = (t: number) => 1 - (1 - t) ** 3

/**
 * Cifra que, al cambiar, cuenta desde lo que se ve hasta el valor nuevo. Comunica "este dato acaba de
 * cambiar" sin una alerta. El primer render muestra el valor final (también en el servidor), así que
 * la carga inicial no hace conteos decorativos. Con reduced-motion el cambio es inmediato.
 * Los lectores de pantalla solo reciben el valor final.
 */
export function NumeroAnimado({ valor, formato = formatoBase, duracion = DURACION_MAXIMA_MS, className }: NumeroAnimadoProps) {
  const [mostrado, setMostrado] = useState(valor)
  // Cifra visible en cada instante: si llega un valor nuevo a mitad de un conteo, el siguiente
  // arranca desde lo que se ve, no desde el objetivo anterior (revisión de Codex F0-02).
  const visible = useRef(valor)

  useEffect(() => {
    const desde = visible.current
    if (desde === valor) return
    const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Saltos pequeños duran menos: cambiar 3 → 4 no debe tardar lo mismo que 0 → 1.988.
    const total = reducido ? 0 : Math.min(duracion, DURACION_MAXIMA_MS, 200 + Math.abs(valor - desde) * 20)
    const inicio = performance.now()
    let marco = requestAnimationFrame(function paso(ahora) {
      const t = total === 0 ? 1 : Math.min(1, (ahora - inicio) / total)
      const actual = desde + (valor - desde) * salidaCubica(t)
      visible.current = actual
      setMostrado(actual)
      if (t < 1) marco = requestAnimationFrame(paso)
    })
    return () => cancelAnimationFrame(marco)
  }, [valor, duracion])

  return (
    <span className={className}>
      <span aria-hidden="true" className="tabular-nums">
        {formato(mostrado)}
      </span>
      <span className="sr-only">{formato(valor)}</span>
    </span>
  )
}
