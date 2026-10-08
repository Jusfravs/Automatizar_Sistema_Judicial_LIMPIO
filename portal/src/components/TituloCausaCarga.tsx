'use client'

import { useParams } from 'next/navigation'
import { NumeroCausaCompartido } from '@/components/NumeroCausa'

function decodificar(valor: string): string | null {
  try {
    return decodeURIComponent(valor)
  } catch {
    return null
  }
}

/**
 * Título del esqueleto del detalle de causa. loading.tsx no recibe params, pero la URL ya trae el
 * número: mostrarlo de inmediato da contexto y permite que el número viaje desde la lista mientras
 * cargan los datos.
 */
export function TituloCausaCarga() {
  const { causa } = useParams<{ causa: string }>()
  const numero = causa ? decodificar(causa) : null
  if (!numero) return <span className="block h-8 w-56 max-w-full animate-pulse rounded-control bg-surface-2" />
  return (
    <h1 className="font-mono text-titulo font-semibold tracking-tight text-fg">
      <NumeroCausaCompartido numero={numero}>{numero}</NumeroCausaCompartido>
    </h1>
  )
}
