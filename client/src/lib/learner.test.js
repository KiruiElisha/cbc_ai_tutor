import { test } from 'node:test'
import assert from 'node:assert/strict'
import { streak } from './learner.js'

const at = new Date('2026-10-30T09:00:00')

test('a streak counts the days in a row with learning, up to today', () => {
  assert.equal(streak(['2026-10-30 08:00:00', '2026-10-29 17:00:00', '2026-10-28'], at), 3)
})

test('a streak still stands in the morning before today is done, and breaks after a missed day', () => {
  assert.equal(streak(['2026-10-29', '2026-10-28'], at), 2)
  assert.equal(streak(['2026-10-27', '2026-10-26'], at), 0)
})
