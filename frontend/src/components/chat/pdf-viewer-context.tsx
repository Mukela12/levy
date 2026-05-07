'use client'

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { PdfViewerCitation } from './pdf-viewer'

interface PdfViewerContextValue {
  active: PdfViewerCitation | null
  open: (citation: PdfViewerCitation) => void
  close: () => void
}

const PdfViewerContext = createContext<PdfViewerContextValue | null>(null)

export function PdfViewerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PdfViewerCitation | null>(null)
  const open = useCallback((c: PdfViewerCitation) => setActive(c), [])
  const close = useCallback(() => setActive(null), [])
  const value = useMemo(() => ({ active, open, close }), [active, open, close])
  return <PdfViewerContext.Provider value={value}>{children}</PdfViewerContext.Provider>
}

export function usePdfViewer() {
  const ctx = useContext(PdfViewerContext)
  if (!ctx) throw new Error('usePdfViewer must be used within PdfViewerProvider')
  return ctx
}
