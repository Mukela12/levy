'use client'

/** The same paths and 500ms hamburger-to-close motion as the legacy dashboard menu. */
export function CanopyMenuToggle({ open = false, size = 22 }: { open?: boolean; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={'cp-menu-toggle' + (open ? ' is-open' : '')}
      aria-hidden="true"
    >
      <path
        className="cp-menu-fold"
        d="M27 10 13 10C10.8 10 9 8.2 9 6 9 3.5 10.8 2 13 2 15.2 2 17 3.8 17 6L17 26C17 28.2 18.8 30 21 30 23.2 30 25 28.2 25 26 25 23.8 23.2 22 21 22L7 22"
      />
      <path d="M7 16 27 16" />
    </svg>
  )
}
