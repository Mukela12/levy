'use client'

import { use } from 'react'
import { MatterDetailView } from '@/components/matters/matter-detail-view'

export default function MatterDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <MatterDetailView id={id} />
}
