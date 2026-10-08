import { PageHeader } from '@/components/ui'
import NuevoLoteForm from './NuevoLoteForm'

export const metadata = { title: 'Nuevo lote' }

export default function NuevoLotePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Nuevo lote"
        descripcion="Sube el Excel de causas y elige cómo procesarlo."
        migas={[{ etiqueta: 'Lotes', href: '/lotes' }, { etiqueta: 'Nuevo lote' }]}
      />
      <NuevoLoteForm />
    </div>
  )
}
