'use client'

/**
 * The auth panel's living illustration: the owner's look-login character,
 * whose gaze follows the pointer while the visitor types. Same asset and
 * wiring as his other products (GazeControl view model, xAxis/yAxis in
 * -1..1), tracked from the window so the eyes stay with the cursor over
 * the form, not only over the canvas. Under reduced motion, or before the
 * runtime is ready, the familiar book illustration stands in.
 */

import { useEffect, useRef, useState } from 'react'
import Image from 'next/image'
import { useRive, useViewModel, useViewModelInstance, useViewModelInstanceNumber } from '@rive-app/react-webgl2'
import { Alignment, Fit, Layout } from '@rive-app/webgl2'
import welcome from '../../../public/canopy/onboarding/welcome.png'

export function BookArt() {
  return <Image src={welcome} alt="" priority sizes="(max-width: 800px) 0px, 360px" />
}

export default function RiveAuthScene() {
  const [reduced, setReduced] = useState(false)
  const boxRef = useRef<HTMLDivElement | null>(null)

  const { rive, RiveComponent } = useRive({
    src: '/animations/rive/look-login.riv',
    artboard: 'Main',
    stateMachines: ['State Machine 1'],
    autoplay: true,
    layout: new Layout({ fit: Fit.Contain, alignment: Alignment.Center }),
  })
  const viewModel = useViewModel(rive, { name: 'GazeControl' })
  const viewModelInstance = useViewModelInstance(viewModel, { rive })
  const xAxis = useViewModelInstanceNumber('xAxis', viewModelInstance)
  const yAxis = useViewModelInstanceNumber('yAxis', viewModelInstance)
  const setX = xAxis.setValue
  const setY = yAxis.setValue

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const apply = () => setReduced(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  useEffect(() => {
    if (reduced) return
    const onMove = (e: MouseEvent) => {
      const box = boxRef.current?.getBoundingClientRect()
      if (!box) return
      const cx = box.left + box.width / 2
      const cy = box.top + box.height / 2
      const reach = Math.max(window.innerWidth, window.innerHeight) / 2
      setX(Math.max(-1, Math.min(1, (e.clientX - cx) / reach)))
      setY(Math.max(-1, Math.min(1, (e.clientY - cy) / reach)))
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMove)
  }, [reduced, setX, setY])

  if (reduced) return <BookArt />

  return (
    <div ref={boxRef} className="cp-auth-rive" aria-hidden="true">
      {!rive && <BookArt />}
      <RiveComponent style={{ width: '100%', height: '100%', display: rive ? 'block' : 'none' }} />
    </div>
  )
}
