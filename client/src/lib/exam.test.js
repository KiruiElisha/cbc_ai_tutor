import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mark, examName } from './exam.js'

const q = (name, area, right) => ({
  name,
  area,
  options: [{ id: 'a', is_correct: right === 'a' ? 1 : 0 }, { id: 'b', is_correct: right === 'b' ? 1 : 0 }],
})

test('the paper is marked overall and per area, weakest area first', () => {
  const questions = [q('1', 'Maths', 'a'), q('2', 'Maths', 'a'), q('3', 'English', 'b')]
  const r = mark(questions, { 1: 'a', 2: 'b', 3: 'b' })
  assert.equal(r.right, 2)
  assert.equal(r.score, 67)
  assert.deepEqual(r.areas.map((a) => [a.area, a.right, a.total]), [['Maths', 1, 2], ['English', 1, 1]])
})

test('a skipped question counts as wrong', () => {
  assert.equal(mark([q('1', 'Maths', 'a')], {}).right, 0)
})

test('the paper is named after the national assessment for that grade', () => {
  assert.equal(examName('Grade 6'), 'KPSEA practice')
  assert.equal(examName('Grade 9'), 'KJSEA practice')
  assert.equal(examName('Grade 4'), 'Exam practice')
})
