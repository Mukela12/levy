/**
 * Levy's loader: three short lines filling and fading in turn, like a page
 * being read. One shared animation for every wait that fills a screen or a
 * panel, in place of the mixed spinners (emerald, blue, theme green) that were
 * there before. It is deliberately not the logo: the splash screen already
 * shows the mark, and an animated logo reads as branding, not progress.
 *
 * CSS only (canopy.css, .cp-loader), so it runs before React hydrates and
 * costs nothing in the bundle. Reduced motion holds the lines still.
 */
export function CanopyLoader({ label, size = 'md', className = '' }: {
  label?: string
  size?: 'sm' | 'md'
  className?: string
}) {
  return (
    <div className={`cp-loader cp-loader-${size} ${className}`.trim()} role="status" aria-live="polite">
      <span className="cp-loader-lines" aria-hidden="true">
        <i /><i /><i />
      </span>
      {label ? <span className="cp-loader-label">{label}</span> : <span className="sr-only">Loading</span>}
    </div>
  )
}

/** A loader centred in the space a page or panel would fill. */
export function CanopyPageLoader({ label }: { label?: string }) {
  return (
    <div className="cp-page-loader">
      <CanopyLoader label={label} />
    </div>
  )
}
