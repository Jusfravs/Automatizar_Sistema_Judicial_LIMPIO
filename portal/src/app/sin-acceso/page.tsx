'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { Card, CardHeader, CardBody } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
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
      <div className="w-full max-w-md">
        <Card>
          <CardHeader
            titulo="Tu usuario no tiene acceso al portal"
            nivel={2}
          />
          <CardBody>
            <EmptyState
              titulo="Tu usuario no tiene acceso al portal"
              descripcion="Tu cuenta existe, pero no tiene un perfil activo. Pide al administrador del portal que active tu usuario y vuelve a iniciar sesión."
              accion={
                <Button
                  variante="secundario"
                  onClick={handleSignOut}
                  className="w-full"
                >
                  Cerrar sesión
                </Button>
              }
            />
          </CardBody>
        </Card>
      </div>
    </main>
  )
}