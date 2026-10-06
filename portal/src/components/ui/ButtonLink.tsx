import Link from 'next/link'
import type { ComponentProps } from 'react'
import { clasesBoton, type TamanoBoton, type VarianteBoton } from './estilos'

export type ButtonLinkProps = ComponentProps<typeof Link> & {
  variante?: VarianteBoton
  tamano?: TamanoBoton
}

/** Enlace con aspecto de botón (navegación). Para acciones que no navegan, usa Button. */
export function ButtonLink({ variante = 'primario', tamano = 'md', className, ...props }: ButtonLinkProps) {
  return <Link className={clasesBoton({ variante, tamano, className })} {...props} />
}
