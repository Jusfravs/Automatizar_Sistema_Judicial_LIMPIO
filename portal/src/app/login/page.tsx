'use client'

import { useState, FormEvent } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { inicioPorRol } from '@/lib/roles'
import { Card, CardHeader, CardBody } from '@/components/ui/Card'
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
      {/* Panel izquierdo: marca (solo lg+) */}
      <aside className="hidden lg:flex lg:w-[40%] flex-col items-center justify-center bg-nav text-on-nav px-8 py-12">
        <div className="flex flex-col items-center max-w-xs">
          <div className="flex items-center gap-3 mb-6">
            <h1 className="font-serif text-3xl font-semibold">Gestión Judicial</h1>
            <span className="h-12 w-px bg-accent" aria-hidden="true" />
          </div>
          <p className="text-on-nav/70 text-center text-sm leading-relaxed">
            Consulta y clasificación de causas judiciales
          </p>
        </div>
      </aside>

      {/* Panel derecho: formulario */}
      <div className="flex w-full lg:w-[60%] items-center justify-center p-4 sm:p-6 lg:p-12">
        <div className="w-full max-w-sm">
          <Card>
            <CardHeader
              titulo="Iniciar sesión"
              descripcion="Usa tu cuenta del portal"
              nivel={2}
            />
            <CardBody className="space-y-4">
              {error && (
                <Alert tono="peligro" rol="alert">
                  {error}
                </Alert>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <Field
                  label="Correo electrónico"
                  htmlFor="email"
                  ayuda="Tu correo institucional"
                  error={undefined}
                >
                  <Input
                    {...a11yCampo('email', { ayuda: 'Tu correo institucional' })}
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={loading}
                  />
                </Field>

                <Field
                  label="Contraseña"
                  htmlFor="password"
                  ayuda="Tu contraseña del portal"
                  error={undefined}
                >
                  <div className="relative">
                    <Input
                      {...a11yCampo('password', { ayuda: 'Tu contraseña del portal' })}
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={loading}
                    />
                    <Button
                      type="button"
                      variante="fantasma"
                      tamano="sm"
                      onClick={togglePassword}
                      aria-pressed={showPassword}
                      aria-controls="password"
                      className="absolute right-3 top-1/2 -translate-y-1/2"
                    >
                      {showPassword ? 'Ocultar' : 'Mostrar'}
                    </Button>
                  </div>
                </Field>

                <Button
                  type="submit"
                  cargando={loading}
                  className="w-full"
                >
                  {loading ? 'Iniciando sesión…' : 'Iniciar sesión'}
                </Button>
              </form>
            </CardBody>
          </Card>
        </div>
      </div>
    </main>
  )
}