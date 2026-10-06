import { cx } from '@/lib/cx'
import { ButtonLink } from './ButtonLink'
import { clasesBoton } from './estilos'
import { IconoAnterior, IconoSiguiente } from './iconos'

export type PaginationProps = {
  pagina: number
  totalPaginas: number
  /** Construye la URL de la página n (conserva los filtros de la búsqueda). */
  hrefPagina: (n: number) => string
  /** aria-label del nav; cámbialo si hay más de una paginación en la vista. */
  etiqueta?: string
  className?: string
}

/** Paginación por enlaces (funciona sin JavaScript). No se muestra si hay una sola página. */
export function Pagination({ pagina, totalPaginas, hrefPagina, etiqueta = 'Paginación', className }: PaginationProps) {
  if (totalPaginas <= 1) return null
  const hayAnterior = pagina > 1
  const haySiguiente = pagina < totalPaginas
  const inactivo = clasesBoton({ variante: 'secundario', tamano: 'sm', deshabilitado: true })

  return (
    <nav aria-label={etiqueta} className={cx('flex items-center justify-between gap-4', className)}>
      {hayAnterior ? (
        <ButtonLink href={hrefPagina(pagina - 1)} variante="secundario" tamano="sm" rel="prev">
          <IconoAnterior />
          Anterior
        </ButtonLink>
      ) : (
        <span aria-disabled="true" className={inactivo}>
          <IconoAnterior />
          Anterior
        </span>
      )}
      <p className="text-sm text-muted tabular-nums">
        Página <span className="font-semibold text-fg">{pagina}</span> de {totalPaginas}
      </p>
      {haySiguiente ? (
        <ButtonLink href={hrefPagina(pagina + 1)} variante="secundario" tamano="sm" rel="next">
          Siguiente
          <IconoSiguiente />
        </ButtonLink>
      ) : (
        <span aria-disabled="true" className={inactivo}>
          Siguiente
          <IconoSiguiente />
        </span>
      )}
    </nav>
  )
}
