/**
 * Levy brand mark. Uses the static `/levy-logo.svg` file from `public/` so the
 * browser caches it independently and we don't ship the (multi-path) SVG in
 * every JS bundle.
 *
 * `size` is in pixels and applies to BOTH dimensions (the SVG is square).
 */

interface LevyLogoProps {
  size?: number
  className?: string
}

export function LevyLogo({ size = 24, className = '' }: LevyLogoProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/levy-logo.svg"
      alt="Levy"
      width={size}
      height={size}
      className={className}
      style={{ width: size, height: size }}
      draggable={false}
    />
  )
}
