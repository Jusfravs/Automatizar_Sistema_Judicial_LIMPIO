import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'

export default async function LotesPage() {
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

  if (!profile || !profile.activo || (profile.rol !== 'gestor_lotes' && profile.rol !== 'admin')) {
    redirect('/login')
  }

  return (
    <main className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Lotes</h1>
    </main>
  )
}