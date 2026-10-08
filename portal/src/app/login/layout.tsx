import type { Metadata } from 'next'

// La página de login es un componente cliente: el título de la pestaña se declara aquí.
export const metadata: Metadata = { title: 'Iniciar sesión' }

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children
}
