import ProtectedLayout from '@/app/protected-layout'

export default function LotesPage() {
  return (
    <ProtectedLayout allowedRoles={['gestor_lotes', 'admin']}>
      <h1 className="text-2xl font-semibold text-gray-900">Lotes</h1>
    </ProtectedLayout>
  )
}