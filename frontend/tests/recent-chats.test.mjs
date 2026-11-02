// Structural regression guard; the trigger itself was tested on a local Postgres.
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
const read = path => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('chat lists sort and label chats by last activity, not by when they began', () => {
  // Until 2 Nov 2026 every list sorted by created_at and nothing wrote
  // updated_at, so a user's 253-message chat from May, still in daily use,
  // sat last in their list and they twice reported it gone. A trigger now
  // moves updated_at on every saved message
  // (supabase/migrations/20261102000000_chat_last_activity.sql).
  assert.match(read('components/chat/use-recent-sessions.ts'), /\.order\('updated_at', \{ ascending: false \}\)/)
  for (const f of ['components/chat/use-recent-sessions.ts', 'lib/matters.ts',
    'app/(dashboard)/matters/[id]/page.tsx', 'app/(dashboard)/documents/page.tsx']) {
    for (const [, chain] of read(f).matchAll(/\.from\('chat_sessions'\)((?:\s*\.\w+\([^)]*\))*)/g)) {
      assert.ok(!chain.includes(".order('created_at'"), f + ' sorts chats by when they began')
    }
  }
  for (const f of ['components/canopy/shell.tsx', 'components/layout/app-sidebar.tsx']) {
    assert.ok(!/imeAgo\(\w+\.created_at\)/.test(read(f)), f + ' labels chats by when they began')
  }
})
