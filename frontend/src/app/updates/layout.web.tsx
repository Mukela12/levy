import '@/styles/updates.css'
import { UpdatesShell } from '@/components/updates/updates-shell'

export default function UpdatesLayout({ children }: { children: React.ReactNode }) {
  return <UpdatesShell>{children}</UpdatesShell>
}
