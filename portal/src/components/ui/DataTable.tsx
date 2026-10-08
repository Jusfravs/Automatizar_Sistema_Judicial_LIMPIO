import type { ReactNode } from 'react'
import { cx } from '@/lib/cx'
import { EmptyState } from './EmptyState'

export type Columna<T> = {
  /** Clave estable de la columna (key de React). */
  clave: string
  encabezado: ReactNode
  celda: (fila: T) => ReactNode
  /** Clases para th y td en escritorio (alineación, ancho, font-mono…). */
  className?: string
  /** No se muestra en la tarjeta móvil (datos secundarios). */
  ocultarEnMovil?: boolean
  /** Título de la tarjeta móvil. Si ninguna lo es, se usa la primera columna. */
  principal?: boolean
}

export type DataTableProps<T> = {
  columnas: readonly Columna<T>[]
  filas: readonly T[]
  claveFila: (fila: T) => string | number
  /** Contenido cuando no hay filas. Por defecto, un EmptyState genérico. */
  vacio?: ReactNode
  /** Descripción accesible de la tabla (caption oculto y aria-label de la lista móvil). */
  etiqueta?: string
  className?: string
}

/**
 * Tabla densa en md+ y lista de tarjetas en móvil. Sin estado: funciona como Server Component.
 * Cada celda se renderiza dos veces (tabla y tarjeta; una queda oculta con display:none):
 * no pongas ids fijos ni componentes cliente con estado propio dentro de `celda`.
 */
export function DataTable<T>({ columnas, filas, claveFila, vacio, etiqueta, className }: DataTableProps<T>) {
  if (filas.length === 0) {
    return <>{vacio ?? <EmptyState titulo="Sin resultados" descripcion="No hay registros para mostrar." />}</>
  }

  const principal = columnas.find((c) => c.principal) ?? columnas[0]
  const resto = columnas.filter((c) => c !== principal && !c.ocultarEnMovil)

  return (
    <div className={className}>
      <div className="hidden overflow-x-auto rounded-tarjeta bg-surface shadow-tarjeta md:block">
        <table className="min-w-full text-sm">
          {etiqueta ? <caption className="sr-only">{etiqueta}</caption> : null}
          <thead className="bg-(--tabla-cabecera)">
            <tr>
              {columnas.map((c) => (
                <th
                  key={c.clave}
                  scope="col"
                  className={cx('px-3 py-2 text-left text-rotulo font-semibold uppercase text-muted', c.className)}
                >
                  {c.encabezado}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-subtle">
            {filas.map((fila) => (
              <tr key={claveFila(fila)} className="transition-colors hover:bg-(--tabla-fila-hover)">
                {columnas.map((c) => (
                  <td key={c.clave} className={cx('px-3 py-2 align-top text-fg', c.className)}>
                    {c.celda(fila)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 md:hidden" aria-label={etiqueta}>
        {filas.map((fila) => (
          <li key={claveFila(fila)} className="rounded-tarjeta bg-surface p-4 shadow-tarjeta">
            {principal ? <div className="text-sm font-semibold text-fg">{principal.celda(fila)}</div> : null}
            {resto.length > 0 ? (
              <dl className="mt-3 space-y-2">
                {resto.map((c) => (
                  <div key={c.clave} className="flex items-baseline justify-between gap-4">
                    <dt className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted">{c.encabezado}</dt>
                    <dd className="min-w-0 text-right text-sm text-fg">{c.celda(fila)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
