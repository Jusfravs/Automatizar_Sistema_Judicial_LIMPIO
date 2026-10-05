import ProtectedLayout from '@/app/protected-layout'

export default function LotesLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedLayout>{children}</ProtectedLayout>
}