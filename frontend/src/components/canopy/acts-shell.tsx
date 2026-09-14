'use client'

import { useUiVariant } from '@/lib/ui-variant'
import { PublicShell } from '@/components/layout/public-shell'
import { ChatStreamProvider } from '@/components/chat/chat-stream-context'
import { BriefProvider } from '@/components/chat/brief-context'
import { PdfViewerProvider } from '@/components/chat/pdf-viewer-context'
import { CanopyShell } from './shell'

/** Keep public legislation content server-rendered, without a sign-in gate. */
export function ActsShell({ children }: { children: React.ReactNode }) {
  const { variant } = useUiVariant()
  if (variant !== 'canopy') return <PublicShell>{children}</PublicShell>
  return <ChatStreamProvider><BriefProvider><PdfViewerProvider><CanopyShell>{children}</CanopyShell></PdfViewerProvider></BriefProvider></ChatStreamProvider>
}
