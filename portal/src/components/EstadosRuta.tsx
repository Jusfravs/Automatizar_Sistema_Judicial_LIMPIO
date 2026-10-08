import type { ReactNode } from 'react'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
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

function MarcoCarga({ mensaje, children }: { mensaje: string; children: ReactNode }) {
  return (
    <div className="space-y-6" aria-busy="true">
      <span className="sr-only" role="status">{mensaje}</span>
      <div aria-hidden="true" className="space-y-6">{children}</div>
    </div>
  )
}

function TituloCarga({ ancho }: { ancho: string }) {
  return <span className="block h-5 animate-pulse rounded-control bg-surface-2" style={{ width: ancho }} />
}

function CabeceraCarga({ accion = false, migas = false }: { accion?: boolean; migas?: boolean }) {
  return (
    <div className="space-y-2">
      {migas ? <Skeleton className="h-4 w-44 max-w-full" /> : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <Skeleton className="h-8 w-56 max-w-full" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
        {accion ? <Skeleton className="h-9 w-28" /> : null}
      </div>
    </div>
  )
}

function TablaCarga({ filas = 5 }: { filas?: number }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-tarjeta bg-surface shadow-tarjeta md:block">
        <div className="flex h-9 items-center gap-6 bg-surface-2 px-3">
          <Skeleton className="h-3 w-1/4" />
          <Skeleton className="h-3 w-1/6" />
          <Skeleton className="h-3 w-1/6" />
          <Skeleton className="ml-auto h-3 w-1/6" />
        </div>
        {Array.from({ length: filas }, (_, i) => (
          <div key={i} className="flex h-14 items-center gap-6 border-b border-subtle px-3 last:border-b-0">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-5 w-1/6 rounded-full" />
            <Skeleton className="h-4 w-1/6" />
            <Skeleton className="ml-auto h-4 w-1/6" />
          </div>
        ))}
      </div>
      <div className="space-y-3 md:hidden">
        {Array.from({ length: Math.min(filas, 4) }, (_, i) => (
          <Card key={i} className="space-y-3 p-4">
            <Skeleton className="h-5 w-3/4" />
            <div className="flex justify-between gap-3"><Skeleton className="h-4 w-20" /><Skeleton className="h-5 w-24 rounded-full" /></div>
            <div className="flex justify-between gap-3"><Skeleton className="h-4 w-24" /><Skeleton className="h-4 w-28" /></div>
          </Card>
        ))}
      </div>
    </>
  )
}

export function CargandoLotes() {
  return (
    <MarcoCarga mensaje="Cargando lotes…">
      <CabeceraCarga accion />
      <div className="flex flex-wrap gap-2">
        {[16, 22, 24, 20, 22].map((ancho, i) => <Skeleton key={i} className="h-8 rounded-full" style={{ width: `${ancho * 4}px` }} />)}
      </div>
      <TablaCarga />
    </MarcoCarga>
  )
}

export function CargandoCasos() {
  return (
    <MarcoCarga mensaje="Cargando casos y filtros…">
      <CabeceraCarga />
      <Card>
        <CardBody className="space-y-4 p-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="space-y-2"><Skeleton className="h-4 w-28" /><Skeleton className="h-9 w-full" /></div>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Skeleton className="h-4 w-56 max-w-full" />
            <div className="flex gap-2"><Skeleton className="h-9 w-20" /><Skeleton className="h-9 w-20" /></div>
          </div>
        </CardBody>
      </Card>
      <Skeleton className="h-4 w-20" />
      <TablaCarga filas={6} />
    </MarcoCarga>
  )
}

export function CargandoDetalleLote() {
  return (
    <MarcoCarga mensaje="Cargando el detalle del lote…">
      <CabeceraCarga migas accion />
      <Card>
        <CardHeader titulo={<TituloCarga ancho="5rem" />} acciones={<Skeleton className="h-6 w-24 rounded-full" />} />
        <CardBody><div className="flex flex-wrap justify-between gap-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-12 w-28 max-w-full" />)}</div></CardBody>
      </Card>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader titulo={<TituloCarga ancho="13rem" />} />
          <CardBody className="space-y-5">
            <div className="flex items-end gap-4"><Skeleton className="h-10 w-20" /><Skeleton className="mb-2 h-2 flex-1 rounded-full" /></div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-12" />)}</div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader titulo={<TituloCarga ancho="7rem" />} />
          <CardBody className="space-y-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-5 w-full" />)}</CardBody>
        </Card>
      </div>
    </MarcoCarga>
  )
}

export function CargandoDetalleCaso() {
  return (
    <MarcoCarga mensaje="Cargando el expediente y sus actuaciones…">
      <CabeceraCarga migas accion />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader titulo={<TituloCarga ancho="11rem" />} />
            <CardBody className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 6 }, (_, i) => <div key={i} className="space-y-2"><Skeleton className="h-4 w-24" /><Skeleton className="h-5 w-4/5" /></div>)}
            </CardBody>
          </Card>
          <Card>
            <CardHeader titulo={<TituloCarga ancho="8rem" />} />
            <CardBody className="grid gap-6 sm:grid-cols-2"><Skeleton className="h-28" /><Skeleton className="h-28" /></CardBody>
          </Card>
          <Card>
            <CardHeader titulo={<TituloCarga ancho="7rem" />} />
            <CardBody className="space-y-5">
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="space-y-2 border-b border-subtle pb-5 last:border-b-0 last:pb-0">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-4/5" />
                </div>
              ))}
            </CardBody>
          </Card>
        </div>
        <Card className="self-start">
          <CardHeader titulo={<TituloCarga ancho="8rem" />} />
          <CardBody className="space-y-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-5 w-full" />)}</CardBody>
        </Card>
      </div>
    </MarcoCarga>
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
