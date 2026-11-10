import { ActsShell } from '@/components/canopy/acts-shell'

export default function ActsLayout({ children }: { children: React.ReactNode }) {
  return <ActsShell>{children}</ActsShell>
}
