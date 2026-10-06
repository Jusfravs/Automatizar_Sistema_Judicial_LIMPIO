'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/Button'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { MarcoError } from '@/components/EstadosRuta'

/** Cuerpo común de los error.tsx: registra el error y ofrece reintentar o volver al inicio. */
export function ErrorRuta({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error('Error al mostrar la página:', error)
  }, [error])

  return (
    <MarcoError>
      {error.digest ? <p className="text-xs tabular-nums text-muted">Código: {error.digest}</p> : null}
      <div className="flex flex-wrap justify-center gap-2">
        <Button onClick={() => retry()}>Reintentar</Button>
        <ButtonLink href="/inicio" variante="secundario">
          Ir al inicio
        </ButtonLink>
      </div>
    </MarcoError>
  )
}
