import ProtectedLayout from '@/app/protected-layout'

export default function InicioLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedLayout>{children}</ProtectedLayout>
}