'use client'

/**
 * Canopy's sky toggle: a sculpted sun that slides to a cratered moon as the
 * sky darkens. A real switch (role, aria-checked, keyboard) rather than a
 * hidden checkbox. Styles live in canopy.css under .cp-theme-toggle.
 */
export function CanopyThemeToggle({ dark, onChange }: { dark: boolean; onChange: (dark: boolean) => void }) {
  return (
    <button
      type="button"
      className="cp-theme-toggle"
      role="switch"
      aria-label="Dark mode"
      aria-checked={dark}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => onChange(!dark)}
    >
      <span className="cp-theme-sky" aria-hidden="true">
        <span className="cp-theme-night" />
        <span className="cp-theme-clouds" />
        <span className="cp-theme-stars"><i /><i /><i /></span>
        <span className="cp-theme-orbit">
          <span className="cp-theme-sun">
            <span className="cp-theme-moon"><i /><i /><i /></span>
          </span>
        </span>
      </span>
    </button>
  )
}
