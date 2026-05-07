'use client'

import React, { useRef, useId, useEffect } from 'react'
import { animate, useMotionValue, type AnimationPlaybackControls } from 'framer-motion'

function mapRange(value: number, fromLow: number, fromHigh: number, toLow: number, toHigh: number): number {
  if (fromLow === fromHigh) return toLow
  const percentage = (value - fromLow) / (fromHigh - fromLow)
  return toLow + percentage * (toHigh - toLow)
}

interface EtherealShadowProps {
  color?: string
  scale?: number
  speed?: number
  className?: string
}

export function EtherealShadow({
  color = 'rgba(0, 100, 50, 0.8)',
  scale = 50,
  speed = 40,
  className,
}: EtherealShadowProps) {
  const rawId = useId()
  const id = `ethereal-${rawId.replace(/:/g, '')}`
  const feColorMatrixRef = useRef<SVGFEColorMatrixElement>(null)
  const hueRotateMotionValue = useMotionValue(180)
  const hueRotateAnimation = useRef<AnimationPlaybackControls | null>(null)

  const displacementScale = mapRange(scale, 1, 100, 20, 100)
  const animationDuration = mapRange(speed, 1, 100, 1000, 50)

  useEffect(() => {
    if (feColorMatrixRef.current) {
      if (hueRotateAnimation.current) hueRotateAnimation.current.stop()
      hueRotateMotionValue.set(0)
      hueRotateAnimation.current = animate(hueRotateMotionValue, 360, {
        duration: animationDuration / 25,
        repeat: Infinity,
        repeatType: 'loop',
        repeatDelay: 0,
        ease: 'linear',
        delay: 0,
        onUpdate: (value: number) => {
          if (feColorMatrixRef.current) {
            feColorMatrixRef.current.setAttribute('values', String(value))
          }
        },
      })
      return () => { hueRotateAnimation.current?.stop() }
    }
  }, [animationDuration, hueRotateMotionValue])

  return (
    <div
      className={className}
      style={{ overflow: 'hidden', position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    >
      <div style={{ position: 'absolute', inset: -displacementScale, filter: `url(#${id}) blur(4px)` }}>
        <svg style={{ position: 'absolute' }}>
          <defs>
            <filter id={id}>
              <feTurbulence result="undulation" numOctaves="2" baseFrequency={`${mapRange(scale, 0, 100, 0.001, 0.0005)},${mapRange(scale, 0, 100, 0.004, 0.002)}`} seed="0" type="turbulence" />
              <feColorMatrix ref={feColorMatrixRef} in="undulation" type="hueRotate" values="180" />
              <feColorMatrix in="dist" result="circulation" type="matrix" values="4 0 0 0 1  4 0 0 0 1  4 0 0 0 1  1 0 0 0 0" />
              <feDisplacementMap in="SourceGraphic" in2="circulation" scale={displacementScale} result="dist" />
              <feDisplacementMap in="dist" in2="undulation" scale={displacementScale} result="output" />
            </filter>
          </defs>
        </svg>
        <div
          style={{
            backgroundColor: color,
            maskImage: `url('https://framerusercontent.com/images/ceBGguIpUU8luwByxuQz79t7To.png')`,
            maskSize: 'cover',
            maskRepeat: 'no-repeat',
            maskPosition: 'center',
            width: '100%',
            height: '100%',
          }}
        />
      </div>
    </div>
  )
}
