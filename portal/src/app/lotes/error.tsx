'use client'

import { ErrorRuta } from '@/components/ErrorRuta'

export default function Error(props: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorRuta {...props} />
}
