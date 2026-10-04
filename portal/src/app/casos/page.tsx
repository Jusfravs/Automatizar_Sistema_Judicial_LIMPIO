import ProtectedLayout from '@/app/protected-layout'
import { ROLES_CASOS } from '@/lib/roles'

export default function CasosPage() {
  return (
    <ProtectedLayout allowedRoles={ROLES_CASOS}>
      <h1 className="text-2xl font-semibold text-gray-900">Casos</h1>
    </ProtectedLayout>
  )
}