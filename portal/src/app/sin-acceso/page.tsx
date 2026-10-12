'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { PantallaEstado } from '@/components/PantallaEstado'
import { Button } from '@/components/ui/Button'
import { IconoCandado } from '@/components/ui/iconos'

export default function SinAccesoPage() {
  const router = useRouter()
  const supabase = useMemo(() => createClient(), [])
  const [correo, setCorreo] = useState<string | null>(null)
  const [saliendo, setSaliendo] = useState(false)

  // Con qué cuenta se entró: es lo primero que necesita saber quien llega aquí.
  useEffect(() => {
    let vigente = true
    supabase.auth.getUser().then(({ data }) => {
      if (vigente) setCorreo(data.user?.email ?? null)
    })
    return () => {
      vigente = false
    }
  }, [supabase])

  async function handleSignOut() {
    setSaliendo(true)
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <PantallaEstado
      Icono={IconoCandado}
      titulo="Tu usuario no tiene acceso al portal"
      acciones={
        <Button onClick={handleSignOut} cargando={saliendo}>
          Cerrar sesión e ingresar con otra cuenta
        </Button>
      }
    >
      {correo ? (
        <p>
          Iniciaste sesión como <span className="font-medium text-fg [overflow-wrap:anywhere]">{correo}</span>.
        </p>
      ) : null}
      <p>
        Tu cuenta existe, pero no tiene un perfil activo. Pide al administrador del portal que active tu usuario y vuelve a
        iniciar sesión.
      </p>
    </PantallaEstado>
  )
}
