import Link from 'next/link'
import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from './estilos'

export type Miga = { etiqueta: string; href?: string }

export type PageHeaderProps = {
  titulo: ReactNode
  descripcion?: ReactNode
  acciones?: ReactNode
  /** Migas de pan; la última es la página actual y no lleva enlace. */
  migas?: readonly Miga[]
  /** Para títulos que son un número de causa o un identificador (system.md 2.3: van en mono, no en serif). */
  tituloMono?: boolean
  className?: string
}

export function PageHeader({ titulo, descripcion, acciones, migas, tituloMono = false, className }: PageHeaderProps) {
  return (
    <header className={cx('space-y-2', className)}>
      {migas && migas.length > 0 ? (
        <nav aria-label="Migas de pan">
          <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
            {migas.map((miga, i) => {
              const ultima = i === migas.length - 1
              return (
                <li key={`${miga.etiqueta}-${i}`} className="flex min-w-0 items-center gap-1.5">
                  {i > 0 ? <span aria-hidden="true">/</span> : null}
                  {miga.href && !ultima ? (
                    <Link
                      href={miga.href}
                      className={cx('rounded-control underline-offset-4 transition-colors hover:text-fg hover:underline', FOCO)}
                    >
                      {miga.etiqueta}
                    </Link>
                  ) : (
                    <span aria-current={ultima ? 'page' : undefined} className={cx('truncate', ultima && 'font-medium text-fg')}>
                      {miga.etiqueta}
                    </span>
                  )}
                </li>
              )
            })}
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 space-y-1">
          <h1
            className={cx(
              'text-2xl font-semibold text-fg text-balance',
              tituloMono ? 'font-mono tracking-tight' : 'font-serif',
            )}
          >
            {titulo}
          </h1>
          {descripcion ? <p className="max-w-prose text-sm text-muted text-pretty">{descripcion}</p> : null}
        </div>
        {acciones ? <div className="flex flex-wrap items-center gap-2">{acciones}</div> : null}
      </div>
    </header>
  )
}
