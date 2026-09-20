import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
const feed = JSON.parse(fs.readFileSync(new URL('../src/data/focus-topics.json', import.meta.url)))
test('weekly edition has bounded dates and original safe sources', () => {
  const start = Date.parse(feed.reviewed), end = Date.parse(feed.expires)
  assert.ok(Number.isFinite(start) && end > start && end - start <= 8 * 86400000)
  // A review dated ahead of today hides the panel until that day. Compare in
  // Lusaka, as the component does: at 01:00 in Lusaka it is still yesterday in UTC.
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lusaka', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  assert.ok(feed.reviewed <= today, `reviewed ${feed.reviewed} is ahead of ${today} in Lusaka`)
  assert.ok(feed.topics.length > 0 && feed.topics.length <= 7)
  const ids = new Set()
  for (const item of feed.topics) {
    assert.ok(!ids.has(item.id)); ids.add(item.id)
    assert.ok(item.question.length <= 140 && item.status && item.published && item.sourceTitle)
    const url = new URL(item.url)
    assert.equal(url.protocol, 'https:')
    assert.ok(!url.username && !url.password)
    assert.ok(url.hostname.endsWith('.gov.zm') || url.hostname === 'judiciaryzambia.com')
  }
})
test('new 3D assets are present as PNGs with alpha-capable color type', () => {
  for (const name of ['irac-scales']) {  // matters-case.png left with the Matters redesign
    const data = fs.readFileSync(new URL(`../public/assets/canopy-actions/${name}.png`, import.meta.url))
    assert.equal(data.subarray(1,4).toString(), 'PNG')
    assert.equal(data[25], 6)
  }
})
