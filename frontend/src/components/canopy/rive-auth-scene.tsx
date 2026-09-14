'use client'

/**
 * The sign-in teddy. The classic Rive login character, wired to the real
 * form: it watches the pointer, leans in and follows along while the email
 * is typed, covers its eyes for the password, and celebrates or slumps on
 * the submit result. Artboard `Teddy`, state machine `Login Machine`,
 * inputs isChecking / numLook / isHandsUp / trigSuccess / trigFail.
 * Reduced motion, load time and phones fall back to the book illustration.
 */

import { useEffect, useState } from 'react'
import Image from 'next/image'
import { useRive, useStateMachineInput } from '@rive-app/react-webgl2'
import type { StateMachineInput } from '@rive-app/webgl2'
import { Alignment, Fit, Layout } from '@rive-app/webgl2'
import welcome from '../../../public/canopy/onboarding/welcome.png'

/** Rive's state-machine inputs are driven by assignment; the setter lives at
 * module scope so the mutation stays out of the component's own effects. */
function drive(input: StateMachineInput | null, value: number | boolean) {
  if (input) input.value = value
}

export function BookArt() {
  return <Image src={welcome} alt="" priority sizes="(max-width: 800px) 0px, 360px" />
}

export interface AuthSceneState {
  /** Field the visitor is in: the teddy checks the email, hides for the password. */
  field: 'idle' | 'email' | 'password'
  /** Characters typed in the email, so the gaze tracks the caret. */
  emailLen: number
  /** Bumped with each submit outcome so triggers re-fire. */
  signal?: { kind: 'success' | 'fail'; nonce: number }
}

export default function RiveAuthScene({ field, emailLen, signal }: AuthSceneState) {
  const [reduced, setReduced] = useState(false)
  const [mouseLook, setMouseLook] = useState(50)

  const { rive, RiveComponent } = useRive({
    src: '/animations/rive/login-teddy.riv',
    artboard: 'Teddy',
    stateMachines: ['Login Machine'],
    autoplay: true,
    layout: new Layout({ fit: Fit.Contain, alignment: Alignment.Center }),
  })
  const isChecking = useStateMachineInput(rive, 'Login Machine', 'isChecking')
  const numLook = useStateMachineInput(rive, 'Login Machine', 'numLook')
  const isHandsUp = useStateMachineInput(rive, 'Login Machine', 'isHandsUp')
  const trigSuccess = useStateMachineInput(rive, 'Login Machine', 'trigSuccess')
  const trigFail = useStateMachineInput(rive, 'Login Machine', 'trigFail')

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const apply = () => setReduced(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  // Idle gaze follows the pointer across the window.
  useEffect(() => {
    if (reduced) return
    const onMove = (e: MouseEvent) => setMouseLook((e.clientX / window.innerWidth) * 100)
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => window.removeEventListener('mousemove', onMove)
  }, [reduced])

  useEffect(() => {
    if (!rive || reduced) return
    drive(isChecking, field === 'email')
    drive(isHandsUp, field === 'password')
    drive(numLook, field === 'email' ? Math.min(100, emailLen * 3.4) : mouseLook)
  }, [rive, reduced, field, emailLen, mouseLook, isChecking, isHandsUp, numLook])

  useEffect(() => {
    if (!rive || reduced || !signal) return
    if (signal.kind === 'success') trigSuccess?.fire()
    else trigFail?.fire()
  }, [rive, reduced, signal, trigSuccess, trigFail])

  if (reduced) return <BookArt />

  return (
    <div className="cp-auth-rive" aria-hidden="true">
      {!rive && <BookArt />}
      <RiveComponent style={{ width: '100%', height: '100%', display: rive ? 'block' : 'none' }} />
    </div>
  )
}
