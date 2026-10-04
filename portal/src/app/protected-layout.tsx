import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import Link from 'next/link'

interface NavBarProps {
  children: React.ReactNode
  userRole: string
  userName: string
}

async function NavBar({ children, userRole, userName }: NavBarProps) {
  const roleLabels: Record<string, string> = {
    gestor_lotes: 'Gestor de Lotes',
    gestor_casos: 'Gestor de Casos',
    admin: 'Administrador',
  }

  const menuItems: Record<string, { href: string; label: string }[]> = {
    gestor_lotes: [{ href: '/lotes', label: 'Lotes' }],
    gestor_casos: [{ href: '/casos', label: 'Casos' }],
    admin: [
      { href: '/lotes', label: 'Lotes' },
      { href: '/casos', label: 'Casos' },
    ],
  }

  const userMenu = menuItems[userRole] || []

  return (
    <header className="border-b border-gray-200 bg-white">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4" aria-label="Navegación principal">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-gray-900">
            {userName}
          </span>
          <span className="hidden sm:inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">
            {roleLabels[userRole] || userRole}
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:flex md:items-center md:gap-4">
            {userMenu.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm font-medium text-gray-700 hover:text-blue-600"
              >
                {item.label}
              </Link>
            ))}
          </div>

          <form action="/api/auth/signout" method="POST">
            <button
              type="submit"
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Cerrar sesión
            </button>
          </form>
        </div>
      </nav>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </header>
  )
}

export default async function ProtectedLayout({
  children,
  allowedRoles,
}: {
  children: React.ReactNode
  allowedRoles: string[]
}) {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const { data: profile } = await supabase
    .from('perfiles')
    .select('rol, activo, nombre')
    .eq('id', user.id)
    .single()

  if (!profile || !profile.activo) {
    redirect('/sin-acceso')
  }

  if (!allowedRoles.includes(profile.rol)) {
    const redirectMap: Record<string, string> = {
      gestor_lotes: '/lotes',
      gestor_casos: '/casos',
      admin: '/lotes',
    }
    redirect(redirectMap[profile.rol] || '/lotes')
  }

  return (
    <NavBar userRole={profile.rol} userName={profile.nombre || user.email || 'Usuario'}>
      {children}
    </NavBar>
  )
}