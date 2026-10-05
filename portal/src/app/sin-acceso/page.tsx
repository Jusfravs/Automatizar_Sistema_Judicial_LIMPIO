'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

export default function SinAccesoPage() {
  const router = useRouter()
  const supabase = createClient()

  async function handleSignOut() {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-sm text-center">
        <h1 className="mb-4 text-2xl font-semibold text-gray-900">
          Tu usuario no tiene acceso al portal
        </h1>
        <p className="mb-6 text-gray-600">
          No tienes un perfil activo o tu rol no permite acceder a esta aplicación.
        </p>
        <button
          onClick={handleSignOut}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
        >
          Cerrar sesión
        </button>
      </div>
    </main>
  )
}