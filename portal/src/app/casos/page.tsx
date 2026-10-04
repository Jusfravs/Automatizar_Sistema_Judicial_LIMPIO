import ProtectedLayout from '@/app/protected-layout'

export default function CasosPage() {
  return (
    <ProtectedLayout allowedRoles={['gestor_casos', 'admin']}>
      <h1 className="text-2xl font-semibold text-gray-900">Casos</h1>
    </ProtectedLayout>
  )
}