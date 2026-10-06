'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { Card, CardBody } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

export default function SinAccesoPage() {
  const router = useRouter()
  const supabase = createClient()

  async function handleSignOut() {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg p-4 sm:p-6">
      <Card className="w-full max-w-md">
        <CardBody className="space-y-6 text-center">
          <div className="space-y-2">
            <h1 className="font-serif text-2xl font-semibold text-balance text-fg">Tu usuario no tiene acceso al portal</h1>
            <p className="text-sm text-pretty text-muted">
              Tu cuenta existe, pero no tiene un perfil activo. Pide al administrador del portal que active tu usuario y
              vuelve a iniciar sesión.
            </p>
          </div>
          <Button variante="secundario" onClick={handleSignOut} className="w-full">
            Cerrar sesión
          </Button>
        </CardBody>
      </Card>
    </main>
  )
}
