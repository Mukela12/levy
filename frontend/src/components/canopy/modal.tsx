'use client'

import { Dialog } from '@base-ui/react/dialog'
import { X } from 'lucide-react'

/** Shared focus management, Escape and focus restoration for Canopy dialogs. */
export function CanopyModal({ title, onClose, children, wide = false }: {
  title: string
  onClose: () => void
  children: React.ReactNode
  wide?: boolean
}) {
  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose() }}>
    <Dialog.Portal>
      <div className="cp-modal">
        <Dialog.Backdrop className="cp-modal-backdrop" />
        <Dialog.Popup className={'cp-modal-panel' + (wide ? ' is-wide' : '')}>
          <div className="cp-modal-head">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="cp-icon-btn" aria-label="Close dialog"><X size={20} /></Dialog.Close>
          </div>
          <div className="cp-modal-body">{children}</div>
        </Dialog.Popup>
      </div>
    </Dialog.Portal>
  </Dialog.Root>
}
