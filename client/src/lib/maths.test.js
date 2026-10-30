import { test } from 'node:test'
import assert from 'node:assert/strict'
import { drill, expression, isRight, solve, topicsFor } from './maths.js'

test('a plain arithmetic question is answered exactly, with its working', () => {
  const r = solve('What is 3 x 4 + 10 ÷ 2?')
  assert.equal(r.answer, '17')
  assert.deepEqual(r.steps, ['3 × 4 = 12', '10 ÷ 2 = 5', '12 + 5 = 17'])
})

test('fractions stay exact and are shown as mixed numbers', () => {
  assert.equal(solve('3/4 + 1/2').answer, '1 1/4')
  assert.equal(solve('3/4 + 1/2').decimal, '1.25')
  assert.deepEqual(solve('3/4 + 1/2').steps, ['3/4 + 1/2 = 1 1/4'])
  assert.deepEqual(solve('12 / 4').steps, ['12 ÷ 4 = 3'])
})

test('decimals, brackets, negatives and Kiswahili words are understood', () => {
  assert.equal(solve('0.1 + 0.2').answer, '3/10')
  assert.equal(solve('(2 + 3) * 4').answer, '20')
  assert.equal(solve('-5 + 2').answer, '-3')
  assert.equal(solve('12 mara 3').answer, '36')
  assert.equal(solve('25% of 200').answer, '50')
})

test('anything that is not plain arithmetic goes to Mwalimu instead', () => {
  assert.equal(solve('What is photosynthesis?'), null)
  assert.equal(solve('Explain 3 states of matter'), null)
  assert.equal(expression('hello'), null)
  assert.equal(solve('5 / 0'), null)
})

test('drills suit the grade and the same seed replays the same questions', () => {
  assert.deepEqual(topicsFor('Grade 1').map((t) => t.key), ['count', 'add', 'subtract'])
  assert.ok(topicsFor('Grade 8').some((t) => t.key === 'equations'))
  const a = drill('Grade 4', 'times', 5, 'seed-1')
  assert.deepEqual(a, drill('Grade 4', 'times', 5, 'seed-1'))
  for (const q of a) {
    assert.equal(solve(q.prompt.replace('= ?', '')).answer, q.answer)
    assert.ok(q.options.includes(q.answer))
    assert.equal(new Set(q.options).size, q.options.length)
  }
})

test('an answer is right in any equivalent form', () => {
  assert.ok(isRight('3 1/2', '7/2'))
  assert.ok(isRight('3.5', '3 1/2'))
  assert.ok(isRight('KES 1,250', '1250'))
  assert.ok(!isRight('', '0'))
  assert.ok(!isRight('4', '5'))
})
