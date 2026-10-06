import { ESTADO_CASO_ETIQUETAS, ESTADO_CASO_TONOS } from '@/lib/casos'
import { ESTADO_ETIQUETAS, ESTADO_TONOS } from '@/lib/lotes'
import { Badge, type BadgeProps } from './Badge'

const MAPAS = {
  lote: { tonos: ESTADO_TONOS, etiquetas: ESTADO_ETIQUETAS },
  caso: { tonos: ESTADO_CASO_TONOS, etiquetas: ESTADO_CASO_ETIQUETAS },
} as const

export type EstadoBadgeProps = Omit<BadgeProps, 'tono' | 'children'> & {
  tipo: keyof typeof MAPAS
  estado: string
}

/**
 * Chip de estado de dominio. Tono y etiqueta salen de src/lib/lotes.ts y src/lib/casos.ts.
 * Estado desconocido: tono neutral con el valor crudo, para no ocultar datos inesperados.
 */
export function EstadoBadge({ tipo, estado, ...props }: EstadoBadgeProps) {
  const { tonos, etiquetas } = MAPAS[tipo]
  return (
    <Badge tono={tonos[estado] ?? 'neutral'} {...props}>
      {etiquetas[estado] ?? estado}
    </Badge>
  )
}
