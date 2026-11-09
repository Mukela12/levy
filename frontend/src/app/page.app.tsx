'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

// The app always opens at the bundle's root; the website serves the chat
// welcome there through a rewrite, which a static export cannot do.
export default function AppStart() {
  const router = useRouter()
  useEffect(() => { router.replace('/chat/') }, [router])
  return null
}
