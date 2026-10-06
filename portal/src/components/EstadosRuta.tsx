import type { ReactNode } from 'react'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { Card, CardBody } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'

/** Esqueleto de página para loading.tsx: cabecera, una fila de tarjetas y un bloque de contenido. */
export function CargandoPagina({ tarjetas = 0 }: { tarjetas?: number }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando…</span>
      <div className="space-y-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      {tarjetas > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: tarjetas }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-tarjeta" />
          ))}
        </div>
      ) : null}
      <Card>
        <CardBody className="space-y-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-5" />
          ))}
        </CardBody>
      </Card>
    </div>
  )
}

/** Contenido de not-found.tsx dentro del AppShell. */
export function NoEncontrado({ titulo, descripcion, volver }: { titulo: string; descripcion: string; volver: { href: string; texto: string } }) {
  return (
    <Card className="mx-auto max-w-lg">
      <CardBody className="space-y-4 text-center">
        <p className="text-sm font-semibold tabular-nums text-muted">404</p>
        <h1 className="font-serif text-2xl font-semibold text-balance text-fg">{titulo}</h1>
        <p className="text-sm text-pretty text-muted">{descripcion}</p>
        <ButtonLink href={volver.href} variante="secundario">
          {volver.texto}
        </ButtonLink>
      </CardBody>
    </Card>
  )
}

/** Marco de error para error.tsx; la parte interactiva (retry) la pone el archivo cliente. */
export function MarcoError({ children }: { children: ReactNode }) {
  return (
    <Card className="mx-auto max-w-lg">
      <CardBody className="space-y-4 text-center">
        <h1 className="font-serif text-2xl font-semibold text-fg">Algo salió mal</h1>
        <p className="text-sm text-pretty text-muted">
          No se pudo mostrar esta página. Puede ser un problema momentáneo de conexión con la base de datos.
        </p>
        {children}
      </CardBody>
    </Card>
  )
}
