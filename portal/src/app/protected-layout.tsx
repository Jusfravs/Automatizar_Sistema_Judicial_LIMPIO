import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { esRolValido } from '@/lib/roles'
import { AppShell } from '@/components/AppShell'

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  // El perfil y el conteo de pendientes son independientes: se piden en paralelo.
  // El conteo solo se usa si el perfil pasa las comprobaciones de acceso.
  const [{ data: profile }, pendientesRes] = await Promise.all([
    supabase.from('perfiles').select('rol, activo, nombre').eq('id', user.id).single(),
    supabase.from('revisiones_ia').select('numero_causa', { count: 'exact', head: true }).eq('estado', 'PENDIENTE'),
  ])

  if (!profile || !profile.activo || !esRolValido(profile.rol)) {
    redirect('/sin-acceso')
  }

  let pendientes: number | null = null
  if (pendientesRes.error) {
    console.error('No se pudieron contar las revisiones pendientes:', pendientesRes.error.message)
  } else {
    pendientes = pendientesRes.count ?? 0
  }

  return (
    <AppShell nombre={profile.nombre || user.email || 'Usuario'} rol={profile.rol} pendientes={pendientes}>
      {children}
    </AppShell>
  )
}
