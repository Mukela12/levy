'use client'

import { useSyncExternalStore, type RefObject } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { X } from 'lucide-react'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useBrief } from '@/components/chat/brief-context'

function subscribeViewport(notify: () => void) {
  const query = window.matchMedia('(min-width: 1101px)')
  query.addEventListener('change', notify)
  return () => query.removeEventListener('change', notify)
}

/** One retained analysis instance, both in the desktop aside and mobile sheet. */
export function CanopyBriefDrawer({ container }: { container: RefObject<HTMLElement | null> }) {
  const brief = useBrief()
  const desktop = useSyncExternalStore(subscribeViewport,
    () => window.matchMedia('(min-width: 1101px)').matches, () => false)
  return (
    <Dialog.Root open={brief.open && brief.available} onOpenChange={brief.setOpen} modal={!desktop} disablePointerDismissal={desktop}>
      <Dialog.Portal container={container} keepMounted>
        <Dialog.Backdrop className="cp-brief-backdrop" />
        <Dialog.Popup className="cp-brief-drawer">
          <Dialog.Title className="sr-only">IRAC analysis</Dialog.Title>
          <Dialog.Description className="sr-only">Generate and export a structured analysis of this conversation.</Dialog.Description>
          <Dialog.Close className="cp-icon-btn cp-brief-close" aria-label="Close IRAC analysis"><X size={18} /></Dialog.Close>
          <BriefPanel messages={brief.messages} token={brief.token} />
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
