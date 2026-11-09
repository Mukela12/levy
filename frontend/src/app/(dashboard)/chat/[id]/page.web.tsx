'use client'

import { use } from 'react'
import { ChatSessionView } from '@/components/chat/chat-session-view'

export default function ChatSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <ChatSessionView id={id} />
}
