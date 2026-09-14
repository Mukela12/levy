// Structural regression guards; browser geometry checks remain necessary.
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
const read = path => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('topbar contains no account avatar or jurisdiction status decoration', () => {
  const header = read('components/canopy/shell.tsx').split('<header className="cp-topbar">')[1].split('</header>')[0]
  assert.ok(!header.includes('/profile'))
  assert.ok(!header.includes('cp-jurisdiction'))
  assert.ok(!header.includes('cp-status-dot'))
})
test('welcome defaults to focus and has no redundant attachment action', () => {
  const source = read('components/canopy/welcome-scene.tsx')
  assert.match(source, /\[focusHidden, setFocusHidden\] = useState\(false\)/)
  assert.match(source, /!hasDraft && \(!focusHidden \? <InFocus/)
  assert.ok(!source.includes('Add a document'))
  assert.ok(!source.includes('onAddDocument'))
})
test('latest-response clearance follows content height, not a negative top offset', () => {
  const css = read('styles/canopy.css')
  const rule = css.match(/\.cp-jump-latest \{([^}]+)\}/)[1]
  assert.match(rule, /bottom: calc\(100% \+ 10px\)/)
  assert.ok(!rule.includes('top:'))
  assert.match(css, /\.cp-harness-foot \{ display: none; \}/)
})
test('legislation keeps its canonical server route and ungated content', () => {
  assert.match(read('app/acts/page.tsx'), /<ActsDirectory acts=\{acts\}>/)
  const shell = read('components/canopy/acts-shell.tsx')
  assert.ok(!shell.includes('if (!user)'))
  assert.match(shell, /<CanopyShell>\{children\}<\/CanopyShell>/)
})
