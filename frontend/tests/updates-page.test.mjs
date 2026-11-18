// The monthly updates at /updates (src/lib/updates.ts).
// The owner's test for these is that they are easy to read, so the checks
// here are about that as much as about the links working.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8')
const out = ts.transpileModule(read('../src/lib/updates.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(out, { exports: exported })
const { updates, getUpdate, longDate } = exported

const prose = (u) => [u.title, u.summary, u.intro, ...(u.smaller || []),
  ...u.sections.flatMap((s) => [s.title, ...s.body, ...(s.how || []), s.tryIt || '', s.note || '', s.image?.caption || ''])]
const sentences = (text) => text.replace(/\*\*|\[|\]\([^)]*\)/g, '').split(/(?<=[.?!])\s+/).filter((x) => /\w/.test(x))

test('one update a month, newest first, each at its own address', () => {
  assert.ok(updates.length >= 4)
  const dates = updates.map((u) => u.date)
  assert.equal(dates.join(), [...dates].sort().reverse().join())
  assert.equal(new Set(updates.map((u) => u.slug)).size, updates.length)
  for (const u of updates) {
    assert.match(u.slug, /^[a-z]+-20\d\d$/)
    assert.match(u.date, /^20\d\d-\d\d-\d\d$/)
    assert.equal(getUpdate(u.slug), u)
  }
  assert.equal(getUpdate('no-such-month'), null)
  assert.equal(longDate('2026-11-18'), '18 November 2026')
})

test('every section can be linked to, and no two share an anchor', () => {
  for (const u of updates) {
    const ids = u.sections.map((s) => s.id)
    assert.equal(new Set(ids).size, ids.length, `${u.slug} repeats an anchor`)
    for (const id of ids) assert.match(id, /^[a-z][a-z0-9-]*$/)
    assert.ok(!ids.includes('smaller-improvements'))        // the page uses that one itself
  }
})

test('it reads easily: short sentences, short paragraphs, plain marks', () => {
  for (const u of updates) {
    const all = prose(u).join(' ')
    assert.ok(!all.includes('—'), `${u.slug}: an em dash`)
    assert.ok(!/["']/.test(all.replace(/\b\w+'\w+\b/g, '')), `${u.slug}: a typewriter quotation mark`)
    const lengths = prose(u).flatMap(sentences).map((x) => x.split(/\s+/).length)      // a title is its own sentence
    const longest = Math.max(...lengths)
    const average = lengths.reduce((a, b) => a + b, 0) / lengths.length
    assert.ok(longest <= 36, `${u.slug}: a sentence of ${longest} words`)
    assert.ok(average <= 19, `${u.slug}: sentences average ${average.toFixed(1)} words`)
    for (const s of u.sections) {
      assert.ok(s.body.length >= 1 && s.body.length <= 3, `${u.slug}#${s.id}: ${s.body.length} paragraphs`)
      for (const p of s.body) assert.ok(sentences(p).length <= 4, `${u.slug}#${s.id}: a paragraph of ${sentences(p).length} sentences`)
    }
  }
})

test('a picture exists, is described, and says when its names are made up', () => {
  for (const u of updates) {
    for (const s of u.sections) {
      if (!s.image) continue
      assert.ok(fs.existsSync(new URL(`../public${s.image.src}`, import.meta.url)), `${s.image.src} is missing`)
      assert.ok(s.image.alt.length > 40 && s.image.caption.length > 10)
      assert.ok(s.image.width > 0 && s.image.height > 0)
    }
  }
  assert.match(getUpdate('november-2026').sections[0].image.caption, /The names are made up\./)
})

test('a question to try is one a person would type', () => {
  for (const u of updates) {
    for (const s of u.sections) {
      if (!s.tryIt) continue
      assert.ok(s.tryIt.length >= 20 && s.tryIt.length <= 160, `${u.slug}#${s.id}`)
      assert.match(s.tryIt, /[.?]$/)
    }
  }
})

test('November says what is a trial, and the figures are the ones measured that day', () => {
  const u = getUpdate('november-2026')
  const z = u.sections.find((s) => s.id === 'zambialii')
  assert.match(z.body[0], /through Laws\.Africa, the service behind ZambiaLII/)
  assert.match(z.note, /This is a trial\. The index gives Levy a summary of the judgment, not its full text/)
  assert.match(u.sections.find((s) => s.id === 'library').body[0], /from 1,165 judgments to 1,665/)
  assert.match(u.sections[0].note, /have a lawyer look at anything you will file or sign/)
})

test('the pages are web-only, and the site map and the footer lead to them', () => {
  for (const f of ['../src/app/updates/layout.web.tsx', '../src/app/updates/page.web.tsx', '../src/app/updates/[slug]/page.web.tsx']) {
    assert.ok(fs.existsSync(new URL(f, import.meta.url)), f)
  }
  assert.match(read('../src/app/sitemap.ts'), /\/updates\/\$\{u\.slug\}/)
  assert.match(read('../src/components/layout/public-shell.tsx'), /href="\/updates"/)
  assert.match(read('../src/app/updates/[slug]/page.web.tsx'), /\/chat\?q=\$\{encodeURIComponent\(s\.tryIt\)\}/)      // pre-fills, never sends
})
