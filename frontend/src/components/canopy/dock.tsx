'use client'

import { useRef } from 'react'
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from 'framer-motion'
import LordIcon from '@/components/ui/lord-icon'
import { CANOPY_ICON } from './icons'
import { CanopyMenuToggle } from './menu-toggle'

// Adapted from the lab's PremiumDock (itself from the component library's dock
// and expandable tabs). Proximity springs for a mouse; stable targets and
// route-owned selection for touch. The current page must stay identifiable,
// so nothing deselects on click-outside.
// `tour` names the onboarding anchor, so the tour can point at the dock on
// the screens where the dock is the navigation.
export type DockDestination = { id: string; label: string; icon: string; href: string; tour?: string }
const spring = { mass: 0.6, stiffness: 420, damping: 34 }

function DockItem({
  item,
  selected,
  go,
  mouseX,
  reduced,
}: {
  item: DockDestination
  selected: boolean
  go: (item: DockDestination) => void
  mouseX: ReturnType<typeof useMotionValue<number>>
  reduced: boolean
}) {
  const ref = useRef<HTMLButtonElement>(null)
  const distance = useTransform(mouseX, (x: number) => {
    const box = ref.current?.getBoundingClientRect()
    return box ? x - box.x - box.width / 2 : Infinity
  })
  const scale = useSpring(useTransform(distance, [-110, 0, 110], [1, 1.13, 1]), spring)
  return (
    <motion.button
      ref={ref}
      type="button"
      className="cp-dock-item"
      aria-label={item.label}
      aria-current={selected ? 'page' : undefined}
      data-tour={item.tour}
      onClick={() => go(item)}
      initial={false}
    >
      {selected && (
        <motion.span
          className="cp-dock-selection"
          layoutId="cp-dock-selection"
          transition={reduced ? { duration: 0 } : spring}
          aria-hidden="true"
        />
      )}
      <motion.span className="cp-dock-icon" style={{ scale: reduced ? 1 : scale }}>
        <LordIcon name={CANOPY_ICON[item.icon]} size={23} />
      </motion.span>
      <span className="cp-dock-label" aria-hidden="true">
        {item.label}
      </span>
    </motion.button>
  )
}

export function CanopyDock({
  destinations,
  activeId,
  moreOpen,
  onMore,
  go,
}: {
  destinations: DockDestination[]
  activeId: string | null
  moreOpen: boolean
  onMore: () => void
  go: (item: DockDestination) => void
}) {
  const reduced = !!useReducedMotion()
  const mouseX = useMotionValue(Infinity)
  const inMain = destinations.some((d) => d.id === activeId)
  return (
    <nav className="cp-dock" aria-label="Quick navigation">
      <div
        className="cp-dock-surface"
        onPointerMove={(e) => {
          if (e.pointerType === 'mouse' && !reduced) mouseX.set(e.clientX)
        }}
        onPointerLeave={() => mouseX.set(Infinity)}
      >
        {destinations.map((item) => (
          <DockItem
            key={item.id}
            item={item}
            selected={activeId === item.id}
            go={go}
            mouseX={mouseX}
            reduced={reduced}
          />
        ))}
      </div>
      <button
        type="button"
        className={'cp-dock-more' + (!inMain ? ' is-current' : '')}
        aria-label="More"
        aria-expanded={moreOpen}
        onClick={onMore}
        data-tour-control="menu"
      >
        <CanopyMenuToggle open={moreOpen} size={23} />
        <span className="cp-dock-label" aria-hidden="true">
          More
        </span>
        {!inMain && <span className="cp-dock-more-dot" aria-hidden="true" />}
      </button>
    </nav>
  )
}
