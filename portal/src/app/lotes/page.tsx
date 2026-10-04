import ProtectedLayout from '@/app/protected-layout'
import { ROLES_LOTES } from '@/lib/roles'

export default function LotesPage() {
  return (
    <ProtectedLayout allowedRoles={ROLES_LOTES}>
      <h1 className="text-2xl font-semibold text-gray-900">Lotes</h1>
    </ProtectedLayout>
  )
}