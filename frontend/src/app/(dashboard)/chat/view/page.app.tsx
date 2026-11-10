'use client'

import { Suspense, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { ChatSessionView } from '@/components/chat/chat-session-view'

// The app's saved-chat page: a static export has no /chat/<id> routes, so the
// id comes from ?id= (see lib/routes.ts).
function FromQuery() {
  const id = useSearchParams().get('id')
  const router = useRouter()
  useEffect(() => { if (!id) router.replace('/chat/') }, [id, router])
  return id ? <ChatSessionView key={id} id={id} /> : null
}

export default function ChatViewPage() {
  return <Suspense fallback={null}><FromQuery /></Suspense>
}
