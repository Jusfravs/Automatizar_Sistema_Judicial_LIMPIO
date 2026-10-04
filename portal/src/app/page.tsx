import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import { inicioPorRol } from '@/lib/roles'

export default async function HomePage() {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const { data: profile } = await supabase
    .from('perfiles')
    .select('rol, activo')
    .eq('id', user.id)
    .single()

  if (!profile || !profile.activo) {
    redirect('/sin-acceso')
  }

  redirect(inicioPorRol(profile.rol))
}