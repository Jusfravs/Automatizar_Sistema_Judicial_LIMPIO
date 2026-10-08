import { NoEncontrado } from '@/components/EstadosRuta'

export default function CausaNoEncontrada() {
  return (
    <NoEncontrado
      titulo="No encontramos esta causa"
      descripcion="Revisa el número de causa o búscala desde el listado."
      volver={{ href: '/casos', texto: 'Volver a casos' }}
    />
  )
}
