import { NoEncontrado } from '@/components/EstadosRuta'

export default function PaginaNoEncontrada() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-bg p-4">
      <NoEncontrado
        titulo="Esta página no existe"
        descripcion="Puede que el enlace esté mal escrito o que la página se haya movido."
        volver={{ href: '/', texto: 'Ir al portal' }}
      />
    </main>
  )
}
