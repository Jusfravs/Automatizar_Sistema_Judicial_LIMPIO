import { describirConfigIa, type ConfigIA } from '@/lib/configIa'

/** Línea discreta bajo el estado del servidor: cómo está trabajando la IA. Sin datos, no ocupa lugar. */
export function ConfigIa({ config }: { config: ConfigIA | null }) {
  if (!config) return null
  const { titulo, detalles } = describirConfigIa(config)
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
      <span className="inline-flex items-center rounded-full bg-neutral-soft px-2.5 py-0.5 text-xs font-medium text-neutral-fg">
        Inteligencia artificial
      </span>
      <span className="text-fg">{titulo}</span>
      {detalles.length > 0 && <span className="text-xs">· {detalles.join(' · ')}</span>}
    </p>
  )
}
