'use client'

import { useEffect, useRef, useState } from 'react'

export type NumeroAnimadoProps = {
  valor: number
  /** Formato visible; por defecto separador de miles es-EC. */
  formato?: (n: number) => string
  /** Duración máxima del conteo (ms). */
  duracion?: number
  className?: string
}

const formatoBase = (n: number) => Math.round(n).toLocaleString('es-EC')

// Sale rápido y se asienta: el ojo lee el valor final antes de que termine.
const salidaCubica = (t: number) => 1 - (1 - t) ** 3

/**
 * Cifra que, al cambiar, cuenta desde el valor anterior hasta el nuevo. Comunica "este dato acaba de
 * cambiar" sin una alerta. El primer render muestra el valor final (también en el servidor), así que
 * la carga inicial no hace conteos decorativos. Con reduced-motion el cambio es inmediato.
 * Los lectores de pantalla solo reciben el valor final.
 */
export function NumeroAnimado({ valor, formato = formatoBase, duracion = 600, className }: NumeroAnimadoProps) {
  const [mostrado, setMostrado] = useState(valor)
  const previo = useRef(valor)

  useEffect(() => {
    const desde = previo.current
    previo.current = valor
    if (desde === valor) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setMostrado(valor)
      return
    }
    // Saltos pequeños duran menos: cambiar 3 → 4 no debe tardar lo mismo que 0 → 1.988.
    const total = Math.min(duracion, 250 + Math.abs(valor - desde) * 25)
    const inicio = performance.now()
    let marco = requestAnimationFrame(function paso(ahora) {
      const t = Math.min(1, (ahora - inicio) / total)
      setMostrado(desde + (valor - desde) * salidaCubica(t))
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
