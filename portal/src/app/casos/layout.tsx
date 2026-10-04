import ProtectedLayout from '@/app/protected-layout'

export default function CasosLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedLayout>{children}</ProtectedLayout>
}