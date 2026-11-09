'use client'

import { Suspense, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { MatterDetailView } from '@/components/matters/matter-detail-view'

// The app's matter page: the id comes from ?id= (see lib/routes.ts).
function FromQuery() {
  const id = useSearchParams().get('id')
  const router = useRouter()
  useEffect(() => { if (!id) router.replace('/matters/') }, [id, router])
  return id ? <MatterDetailView key={id} id={id} /> : null
}

export default function MatterViewPage() {
  return <Suspense fallback={null}><FromQuery /></Suspense>
}
