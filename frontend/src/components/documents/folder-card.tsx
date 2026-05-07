'use client'

import { useState } from 'react'
import { FolderOpen, Lock, Plus } from 'lucide-react'

export type FolderKind = 'global' | 'user' | 'new'

interface FolderCardProps {
  kind: FolderKind
  name: string
  count?: number
  description?: string
  onClick?: () => void
}

/**
 * 3D folder visual that fans documents out on hover. Used to represent the
 * curated Global library, each user-created folder, and the "+ New folder"
 * affordance. Mobile collapses to a flat icon row.
 */
export function FolderCard({ kind, name, count, description, onClick }: FolderCardProps) {
  const [hovered, setHovered] = useState(false)
  const isNew = kind === 'new'
  const isGlobal = kind === 'global'

  const hue = isNew ? 'rgba(255,255,255,0.045)' : 'rgba(34, 197, 94, 0.10)'
  const hueBorder = isNew ? 'rgba(255,255,255,0.08)' : 'rgba(34, 197, 94, 0.18)'
  const hueFlap = isNew ? 'rgba(255,255,255,0.06)' : 'rgba(34, 197, 94, 0.15)'
  const hueFlapBorder = isNew ? 'rgba(255,255,255,0.10)' : 'rgba(34, 197, 94, 0.20)'
  const accent = isNew ? 'text-white/40' : 'text-emerald-400'

  return (
    <button
      type="button"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      className="group p-3.5 sm:p-5 rounded-2xl border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/20 transition-all duration-300 text-left w-full"
    >
      {/* 3D folder visual — same on mobile + desktop, just slightly smaller on
          narrow viewports so two fit cleanly in a row. */}
      <div
        className="flex items-center justify-center mb-3 sm:mb-4 h-20 sm:h-28"
        style={{ perspective: '600px' }}
      >
        <div
          className="relative w-[72px] h-14 sm:w-24 sm:h-20"
          style={{ transformStyle: 'preserve-3d' }}
        >
          {/* Folder back */}
          <div
            className="absolute inset-0 rounded-lg border"
            style={{ background: hue, borderColor: hueBorder, transform: 'rotateX(5deg)', transformOrigin: 'bottom center' }}
          />
          {/* Document cards fanning out (skip for "new folder" — empty) */}
          {!isNew &&
            [0, 1, 2].map((i) => (
              <div
                key={i}
                className="absolute left-2 right-2 sm:left-3 sm:right-3 h-9 sm:h-12 rounded bg-white/[0.04] border border-white/[0.08]"
                style={{
                  bottom: '6px',
                  transform: hovered
                    ? `translateY(${-16 - i * 11}px) rotateX(-2deg) rotateZ(${(i - 1) * 4}deg)`
                    : `translateY(${-2 - i * 2}px) rotateX(0deg) rotateZ(0deg)`,
                  transition: `transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * 0.05}s`,
                  transformOrigin: 'bottom center',
                  zIndex: i,
                }}
              >
                <div className="p-1 sm:p-1.5">
                  <div className="h-[3px] sm:h-1 w-6 sm:w-8 rounded-full bg-white/[0.06]" />
                  <div className="h-[3px] sm:h-1 w-4 sm:w-5 rounded-full bg-white/[0.04] mt-1" />
                </div>
              </div>
            ))}
          {/* Folder front flap */}
          <div
            className="absolute inset-x-0 bottom-0 h-10 sm:h-14 rounded-lg rounded-tl-none border"
            style={{
              background: hueFlap,
              borderColor: hueFlapBorder,
              transform: hovered ? 'rotateX(-35deg)' : 'rotateX(0deg)',
              transformOrigin: 'bottom center',
              transition: 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
              zIndex: 10,
            }}
          />
          {/* Folder tab */}
          <div
            className="absolute top-0 left-0 w-7 h-2 sm:w-10 sm:h-3 rounded-t-md border border-b-0"
            style={{
              background: hueFlap,
              borderColor: hueFlapBorder,
              transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
              transition: 'transform 0.3s ease',
            }}
          />
          {/* Center icon for the "new folder" affordance */}
          {isNew && (
            <Plus
              size={20}
              className="absolute inset-0 m-auto text-white/40 group-hover:text-emerald-400 transition-colors z-20"
            />
          )}
          {/* Lock icon on the global folder */}
          {isGlobal && (
            <Lock
              size={10}
              className="absolute top-1 right-1 text-emerald-300/70 z-20"
              aria-label="Curated, read-only"
            />
          )}
          {/* Hidden — no longer using the simple-icon fallback now that the
              3D visual is mobile-friendly. Keep the import alive. */}
          <span className="hidden">
            <FolderOpen size={1} className={accent} />
          </span>
        </div>
      </div>

      <h3 className="text-[13px] sm:text-[14px] font-semibold text-white/85 truncate">{name}</h3>
      {description ? (
        <p className="text-[11px] sm:text-[11.5px] text-white/35 mt-0.5 line-clamp-2">{description}</p>
      ) : (
        <p className="text-[11px] sm:text-[12px] text-white/30 mt-0.5">
          {typeof count === 'number'
            ? `${count} document${count === 1 ? '' : 's'}`
            : isNew
            ? 'Create a folder'
            : ''}
        </p>
      )}
    </button>
  )
}
