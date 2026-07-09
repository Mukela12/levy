'use client'

import { useEffect, useRef, useState } from 'react'
import Lottie, { type LottieRefCurrentProps } from 'lottie-react'

type Trigger = 'hover' | 'click' | 'loop' | 'none'

interface LordIconProps {
  name: string
  size?: number
  trigger?: Trigger
  className?: string
  style?: React.CSSProperties
  onClick?: () => void
}

export default function LordIcon({
  name,
  size = 24,
  trigger = 'hover',
  className = '',
  style,
  onClick,
}: LordIconProps) {
  const lottieRef = useRef<LottieRefCurrentProps | null>(null)
  const [animationData, setAnimationData] = useState<object | null>(null)

  useEffect(() => {
    const cleanName = name.endsWith('.json') ? name : `${name}.json`
    fetch(`/icons/lordicon/${cleanName}`)
      .then((res) => res.json())
      .then(setAnimationData)
      .catch(console.error)
  }, [name])

  if (!animationData) {
    return <div style={{ width: size, height: size }} className={className} />
  }

  const handleMouseEnter = () => {
    if (trigger === 'hover') {
      lottieRef.current?.goToAndPlay(0)
    }
  }

  const handleClick = () => {
    if (trigger === 'click') {
      lottieRef.current?.goToAndPlay(0)
    }
    onClick?.()
  }

  return (
    <div
      className={`inline-flex shrink-0 ${className}`}
      style={{ width: size, height: size, ...style }}
      onMouseEnter={handleMouseEnter}
      onClick={handleClick}
    >
      <Lottie
        lottieRef={lottieRef}
        animationData={animationData}
        loop={trigger === 'loop'}
        autoplay={trigger === 'loop'}
        style={{ width: size, height: size }}
        onComplete={() => {
          if (trigger !== 'loop') {
            lottieRef.current?.stop()
          }
        }}
      />
    </div>
  )
}
