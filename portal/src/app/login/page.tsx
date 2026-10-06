'use client'

import { useState, FormEvent } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { inicioPorRol } from '@/lib/roles'
import { Card, CardBody } from '@/components/ui/Card'
import { Field, a11yCampo } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const supabase = createClient()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (signInError) {
      setError('Credenciales inválidas')
      setLoading(false)
      return
    }

    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      setError('No se pudo obtener el usuario')
      setLoading(false)
      return
    }

    const { data: profile, error: profileError } = await supabase
      .from('perfiles')
      .select('rol, activo')
      .eq('id', user.id)
      .single()

    if (profileError || !profile || !profile.activo) {
      router.push('/sin-acceso')
      router.refresh()
      return
    }

    const redirectTo = inicioPorRol(profile.rol)
    router.push(redirectTo)
    router.refresh()
  }

  function togglePassword() {
    setShowPassword((prev) => !prev)
  }

  return (
    <main className="flex min-h-screen bg-bg">
      <aside className="hidden flex-col justify-center bg-nav px-12 py-12 text-on-nav lg:flex lg:w-2/5">
        <div className="max-w-sm space-y-4">
          <div className="flex items-center gap-3">
            <span aria-hidden="true" className="h-10 w-1.5 shrink-0 rounded-full bg-accent" />
            <p className="font-serif text-4xl font-semibold tracking-tight">Gestión Judicial</p>
          </div>
          <p className="text-base leading-relaxed text-on-nav/80">Consulta y clasificación de causas judiciales</p>
        </div>
      </aside>

      <div className="flex w-full flex-col items-center justify-center gap-8 p-4 sm:p-6 lg:w-3/5 lg:p-12">
        <div className="flex items-center gap-2.5 lg:hidden">
          <span aria-hidden="true" className="h-6 w-1 shrink-0 rounded-full bg-accent" />
          <p className="font-serif text-xl font-semibold tracking-tight text-fg">Gestión Judicial</p>
        </div>

        <Card className="w-full max-w-sm">
          <CardBody className="space-y-6">
            <div className="space-y-1">
              <h1 className="font-serif text-2xl font-semibold text-fg">Iniciar sesión</h1>
              <p className="text-sm text-muted">Usa tu cuenta del portal</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <Field label="Correo electrónico" htmlFor="email">
                <Input
                  {...a11yCampo('email', {})}
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />
              </Field>

              <Field label="Contraseña" htmlFor="password">
                <div className="relative">
                  <Input
                    {...a11yCampo('password', {})}
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={loading}
                    className="pr-24"
                  />
                  <Button
                    type="button"
                    variante="fantasma"
                    tamano="sm"
                    onClick={togglePassword}
                    aria-pressed={showPassword}
                    aria-controls="password"
                    className="absolute right-1 top-1/2 -translate-y-1/2"
                  >
                    {showPassword ? 'Ocultar' : 'Mostrar'}
                  </Button>
                </div>
              </Field>

              {error && (
                <Alert tono="peligro" rol="alert">
                  {error}
                </Alert>
              )}

              <Button type="submit" cargando={loading} className="w-full">
                {loading ? 'Iniciando sesión…' : 'Iniciar sesión'}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </main>
  )
}
