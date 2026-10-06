import { NoEncontrado } from '@/components/EstadosRuta'

export default function LoteNoEncontrado() {
  return (
    <NoEncontrado
      titulo="No encontramos este lote"
      descripcion="Puede que el enlace esté mal escrito o que el lote ya no exista."
      volver={{ href: '/lotes', texto: 'Volver a lotes' }}
    />
  )
}
