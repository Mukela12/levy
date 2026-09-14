'use client'

/**
 * Lottie icon wrapper for the local Lordicon JSON files.
 *
 * Triggers:
 *  - 'hover' (default): plays once when the nearest button or link is
 *    hovered, focused, clicked or tapped. Binding to the parent control,
 *    not this span, is what makes the dock and big cards animate on touch
 *    screens, where nothing ever hovers.
 *  - 'loop': plays continuously (decorative surfaces that should feel alive).
 *  - 'none': static.
 * Reduced motion wins over every trigger: the icon holds its first frame.
 */

import { useEffect, useRef, useState } from 'react'
import Lottie, { type LottieRefCurrentProps } from 'lottie-react'

type Trigger = 'hover' | 'click' | 'loop' | 'periodic' | 'none'

interface LordIconProps {
  name: string
  size?: number
  trigger?: Trigger
  /** 'periodic' only: milliseconds between replays (default 30s). */
  intervalMs?: number
  /** 'periodic' only: offset before the first replay, so neighbours stagger. */
  delayMs?: number
  className?: string
  style?: React.CSSProperties
  onClick?: () => void
}

export default function LordIcon({
  name,
  size = 24,
  trigger = 'hover',
  intervalMs = 30000,
  delayMs = 0,
  className = '',
  style,
  onClick,
}: LordIconProps) {
  const lottieRef = useRef<LottieRefCurrentProps | null>(null)
  const boxRef = useRef<HTMLDivElement | null>(null)
  const [animationData, setAnimationData] = useState<object | null>(null)

  useEffect(() => {
    let alive = true
    const cleanName = name.endsWith('.json') ? name : `${name}.json`
    fetch(`/icons/lordicon/${cleanName}`)
      .then((res) => res.json())
      .then((data) => { if (alive) setAnimationData(data) })
      .catch(console.error)
    return () => { alive = false }
  }, [name])

  // A slow heartbeat: play once soon after mount, then again every interval,
  // staggered by delayMs so neighbouring icons take turns.
  useEffect(() => {
    if (!animationData || trigger !== 'periodic') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      lottieRef.current?.goToAndStop(0, true)
      return
    }
    const play = () => lottieRef.current?.goToAndPlay(0, true)
    let timer: ReturnType<typeof setInterval> | undefined
    const first = setTimeout(() => {
      play()
      timer = setInterval(play, intervalMs)
    }, 600 + delayMs)
    return () => {
      clearTimeout(first)
      if (timer) clearInterval(timer)
    }
  }, [animationData, trigger, intervalMs, delayMs])

  // Interaction playback binds to the closest button or link, so pressing
  // anywhere on the control replays the icon (touch included).
  useEffect(() => {
    if (!animationData || trigger === 'loop' || trigger === 'periodic' || trigger === 'none') return
    const box = boxRef.current
    if (!box) return
    const target = (box.closest('button, a') as HTMLElement | null) ?? box
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const play = () => { if (!reduced.matches) lottieRef.current?.goToAndPlay(0, true) }
    target.addEventListener('pointerenter', play)
    target.addEventListener('focus', play)
    target.addEventListener('click', play)
    return () => {
      target.removeEventListener('pointerenter', play)
      target.removeEventListener('focus', play)
      target.removeEventListener('click', play)
    }
  }, [animationData, trigger])

  // Looping surfaces still respect reduced motion.
  useEffect(() => {
    if (!animationData || trigger !== 'loop') return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      lottieRef.current?.goToAndStop(0, true)
    }
  }, [animationData, trigger])

  if (!animationData) {
    return <div ref={boxRef} style={{ width: size, height: size }} className={className} />
  }

  return (
    <div
      ref={boxRef}
      className={`inline-flex shrink-0 ${className}`}
      style={{ width: size, height: size, ...style }}
      onClick={onClick}
    >
      <Lottie
        lottieRef={lottieRef}
        animationData={animationData}
        loop={trigger === 'loop'}
        autoplay={trigger === 'loop'}
        style={{ width: size, height: size }}
        onComplete={() => {
          if (trigger !== 'loop') lottieRef.current?.goToAndStop(0, true)
        }}
      />
    </div>
  )
}
