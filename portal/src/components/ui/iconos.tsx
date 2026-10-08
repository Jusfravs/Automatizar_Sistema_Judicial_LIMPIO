import type { ComponentProps, ReactNode } from 'react'

/*
 * Iconos de trazo (16px, currentColor). Son decorativos: llevan aria-hidden y
 * el texto accesible lo pone siempre el componente que los usa.
 */
type IconoProps = Omit<ComponentProps<'svg'>, 'children'>

function Trazo({ className = 'size-4', ...props }: IconoProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...props}
    />
  )
}

export function IconoInfo(props: IconoProps) {
  return (
    <Trazo {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </Trazo>
  )
}

export function IconoExito(props: IconoProps) {
  return (
    <Trazo {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.5 2.5 2.5 4.5-5" />
    </Trazo>
  )
}

export function IconoPeligro(props: IconoProps) {
  return (
    <Trazo {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5M12 16h.01" />
    </Trazo>
  )
}

export function IconoAtencion(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M10.3 4.2 2.8 17.2A2 2 0 0 0 4.5 20h15a2 2 0 0 0 1.7-2.8L13.7 4.2a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4M12 16.5h.01" />
    </Trazo>
  )
}

export function IconoCerrar(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Trazo>
  )
}

export function IconoMenu(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Trazo>
  )
}

export function IconoInicio(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1Z" />
    </Trazo>
  )
}

export function IconoLotes(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="m12 4 8 4-8 4-8-4Z" />
      <path d="m4 12 8 4 8-4M4 16l8 4 8-4" />
    </Trazo>
  )
}

export function IconoCasos(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" />
    </Trazo>
  )
}

export function IconoSalir(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l4-4-4-4M14 12H4" />
    </Trazo>
  )
}

export function IconoAnterior(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="m15 18-6-6 6-6" />
    </Trazo>
  )
}

export function IconoSiguiente(props: IconoProps) {
  return (
    <Trazo {...props}>
      <path d="m9 18 6-6-6-6" />
    </Trazo>
  )
}

export function IconoBuscar(props: IconoProps) {
  return (
    <Trazo {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Trazo>
  )
}

export function IconoCandado(props: IconoProps) {
  return (
    <Trazo {...props}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Trazo>
  )
}

export function IconoBrujula(props: IconoProps) {
  return (
    <Trazo {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z" />
    </Trazo>
  )
}

/** Indicador de carga. Con reduced-motion globals.css detiene el giro y queda estático. */
export function Spinner({ className = 'size-4 animate-spin', ...props }: IconoProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false" className={className} {...props}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
