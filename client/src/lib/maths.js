/**
 * Maths that needs no AI and no internet: exact answers to arithmetic questions, with the
 * working shown, and endless practice drills for each grade. Mwalimu tries this first, so a
 * learner asking "what is 3/4 + 1/2" gets an instant answer and no AI message is used.
 */

// ---- exact numbers: fractions kept as numerator / denominator ----

const gcd = (a, b) => (b === 0 ? Math.abs(a) : gcd(b, a % b))

export function frac(n, d = 1) {
  if (d === 0) throw new Error('division by zero')
  const sign = d < 0 ? -1 : 1
  const g = gcd(n, d) || 1
  return { n: (sign * n) / g, d: (sign * d) / g }
}

const add = (a, b) => frac(a.n * b.d + b.n * a.d, a.d * b.d)
const sub = (a, b) => frac(a.n * b.d - b.n * a.d, a.d * b.d)
const mul = (a, b) => frac(a.n * b.n, a.d * b.d)
const div = (a, b) => frac(a.n * b.d, a.d * b.n)

/** 7/2 → "3 1/2", 6/3 → "2", 0.75 stays a fraction unless asked. */
export function show(x) {
  if (x.d === 1) return String(x.n)
  const whole = Math.trunc(x.n / x.d)
  const rest = Math.abs(x.n % x.d)
  return whole ? `${whole} ${rest}/${x.d}` : `${x.n}/${x.d}`
}

const asDecimal = (x) => Number((x.n / x.d).toFixed(6)).toString()

// ---- reading a question ----

const WORDS = [
  [/\b(?:what is|what's|calculate|find|work out|solve|evaluate|ni ngapi|hesabu)\b/gi, ''],
  [/\bplus\b|\bjumlisha\b|\bna\b(?=\s*\d)/gi, '+'],
  [/\bminus\b|\btoa\b/gi, '-'],
  [/\b(?:times|multiplied by|mara)\b/gi, '*'],
  [/\b(?:divided by|gawanya kwa)\b/gi, '/'],
  [/[×x](?=\s*[\d(])/gi, '*'],
  [/÷/g, '/'],
  [/[?=]/g, ''],
]

/** Turns "what is 3 x 4?" into "3*4"; null when the text is not plain arithmetic. */
export function expression(text) {
  let s = String(text || '').toLowerCase()
  for (const [re, to] of WORDS) s = s.replace(re, to)
  s = s.replace(/(\d),(\d{3})/g, '$1$2').trim()
  const percentOf = s.match(/^(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)$/)
  if (percentOf) return `${percentOf[1]}/100*${percentOf[2]}`.replace(/\//g, '/ ')
  if (!/^[\d\s.+\-*/()]+$/.test(s) || !/\d/.test(s) || !/[+\-*/]/.test(s.replace(/^-/, ''))) return null
  // "3/4" written without spaces is a fraction, not a division to show as a step.
  return s.replace(/(\d+)\/(\d+)/g, '$1#$2').replace(/\s+/g, '')
}

function tokens(s) {
  const out = []
  for (const m of s.matchAll(/\d+#\d+|\d+(?:\.\d+)?|[+\-*/()]/g)) out.push(m[0])
  return out
}

const decimalToFrac = (t) => {
  const [w, f = ''] = t.split('.')
  return frac(Number(w + f), 10 ** f.length)
}

/** Recursive descent over + - * / ( ), keeping every step for the explanation. */
function evaluate(expr) {
  const t = tokens(expr)
  const steps = []
  let i = 0
  const peek = () => t[i]
  const take = () => t[i++]

  function primary() {
    const tok = take()
    if (tok === '(') {
      const v = sum()
      if (take() !== ')') throw new Error('bracket')
      return v
    }
    if (tok === '-') return mul(frac(-1), primary())
    if (tok === undefined || !/\d/.test(tok)) throw new Error('number')
    if (tok.includes('#')) {
      const [n, d] = tok.split('#').map(Number)
      return frac(n, d)
    }
    return decimalToFrac(tok)
  }

  function product() {
    let v = primary()
    while (peek() === '*' || peek() === '/') {
      const op = take()
      const r = primary()
      const out = op === '*' ? mul(v, r) : div(v, r)
      steps.push(`${show(v)} ${op === '*' ? '×' : '÷'} ${show(r)} = ${show(out)}`)
      v = out
    }
    return v
  }

  function sum() {
    let v = product()
    while (peek() === '+' || peek() === '-') {
      const op = take()
      const r = product()
      const out = op === '+' ? add(v, r) : sub(v, r)
      steps.push(`${show(v)} ${op} ${show(r)} = ${show(out)}`)
      v = out
    }
    return v
  }

  const value = sum()
  if (i !== t.length) throw new Error('extra')
  return { value, steps }
}

/**
 * Answers plain arithmetic with its working, or returns null so the question goes to Mwalimu.
 * The reply is Markdown, in the same voice as the AI tutor.
 */
export function solve(text) {
  const expr = expression(text)
  if (!expr) return null
  let result
  try {
    result = evaluate(expr)
  } catch {
    return null
  }
  const { value, steps } = result
  const answer = show(value)
  const lines = []
  if (steps.length > 1) {
    lines.push('Let us work it out step by step (multiply and divide first, then add and subtract):', '')
    steps.forEach((s, n) => lines.push(`${n + 1}. ${s}`))
    lines.push('')
  }
  lines.push(`**Answer: ${answer}**`)
  if (value.d !== 1) lines.push('', `As a decimal that is about ${asDecimal(value)}.`)
  return { answer, decimal: asDecimal(value), steps, markdown: lines.join('\n') }
}

// ---- practice drills ----

/** A small seeded random generator, so a drill can be replayed and checked. */
export function rng(seed) {
  let s = [...String(seed)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 2166136261)
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const between = (r, lo, hi) => lo + Math.floor(r() * (hi - lo + 1))

/** Grade number from "PP1", "Grade 4", "4". PP1 → -1, PP2 → 0. */
export function gradeNumber(grade) {
  const g = String(grade || '').toUpperCase()
  if (g.includes('PP1')) return -1
  if (g.includes('PP2')) return 0
  const m = g.match(/\d+/)
  return m ? Number(m[0]) : 4
}

const TOPICS = {
  count: { title: 'Counting on', from: -1, to: 1 },
  add: { title: 'Addition', from: 0, to: 6 },
  subtract: { title: 'Subtraction', from: 1, to: 6 },
  times: { title: 'Times tables', from: 2, to: 6 },
  divide: { title: 'Division', from: 3, to: 7 },
  fractions: { title: 'Fractions', from: 3, to: 9 },
  decimals: { title: 'Decimals', from: 5, to: 9 },
  percent: { title: 'Percentages', from: 6, to: 9 },
  money: { title: 'Money (KES)', from: 2, to: 6 },
  equations: { title: 'Simple equations', from: 7, to: 12 },
  integers: { title: 'Positive and negative numbers', from: 7, to: 12 },
}

/** The drills that suit a grade, easiest first. */
export function topicsFor(grade) {
  const g = gradeNumber(grade)
  return Object.entries(TOPICS)
    .filter(([, t]) => g >= t.from && g <= t.to)
    .map(([key, t]) => ({ key, title: t.title }))
}

function question(topic, g, r) {
  const big = g <= 1 ? 10 : g <= 2 ? 20 : g <= 3 ? 100 : 1000
  switch (topic) {
    case 'count': {
      const a = between(r, 1, g < 0 ? 5 : 15)
      const b = between(r, 1, 4)
      return { prompt: `Start at ${a} and count on ${b}. Where do you stop?`, answer: a + b,
        why: `${a} and ${b} more is ${a + b}.` }
    }
    case 'add': {
      const a = between(r, 1, big), b = between(r, 1, big)
      return { prompt: `${a} + ${b} = ?`, answer: a + b, why: `${a} + ${b} = ${a + b}.` }
    }
    case 'subtract': {
      const a = between(r, 2, big), b = between(r, 1, a)
      return { prompt: `${a} − ${b} = ?`, answer: a - b, why: `${a} − ${b} = ${a - b}. Check: ${a - b} + ${b} = ${a}.` }
    }
    case 'times': {
      const a = between(r, 2, g <= 3 ? 5 : 12), b = between(r, 2, 12)
      return { prompt: `${a} × ${b} = ?`, answer: a * b, why: `${a} groups of ${b} make ${a * b}.` }
    }
    case 'divide': {
      const b = between(r, 2, 12), q = between(r, 2, 12)
      return { prompt: `${b * q} ÷ ${b} = ?`, answer: q, why: `${b} × ${q} = ${b * q}, so ${b * q} ÷ ${b} = ${q}.` }
    }
    case 'fractions': {
      const d = [2, 3, 4, 5, 6, 8, 10][between(r, 0, 6)]
      const a = between(r, 1, d - 1), b = between(r, 1, d - 1)
      const sum = frac(a + b, d)
      return { prompt: `${a}/${d} + ${b}/${d} = ?`, answer: show(sum),
        why: `Same denominator, so add the tops: ${a} + ${b} = ${a + b}. That is ${a + b}/${d} = ${show(sum)}.` }
    }
    case 'decimals': {
      const a = between(r, 1, 99) / 10, b = between(r, 1, 99) / 10
      const ans = Math.round((a + b) * 10) / 10
      return { prompt: `${a} + ${b} = ?`, answer: ans, why: `Line up the decimal points: ${a} + ${b} = ${ans}.` }
    }
    case 'percent': {
      const p = [10, 20, 25, 50, 75][between(r, 0, 4)], n = between(r, 2, 40) * 20
      return { prompt: `What is ${p}% of ${n}?`, answer: (p * n) / 100,
        why: `${p}% means ${p} out of 100: ${p}/100 × ${n} = ${(p * n) / 100}.` }
    }
    case 'money': {
      const price = between(r, 2, 40) * 5, paid = Math.ceil((price + 1) / 50) * 50
      return { prompt: `A mandazi costs KES ${price}. You pay KES ${paid}. How much change do you get?`,
        answer: paid - price, why: `${paid} − ${price} = ${paid - price}. The change is KES ${paid - price}.` }
    }
    case 'equations': {
      const x = between(r, 1, 15), a = between(r, 2, 9), b = between(r, 1, 30)
      return { prompt: `Solve for x: ${a}x + ${b} = ${a * x + b}`, answer: x,
        why: `Take away ${b} from both sides: ${a}x = ${a * x}. Divide by ${a}: x = ${x}.` }
    }
    case 'integers': {
      const a = between(r, -20, 20), b = between(r, -20, 20)
      const shown = b < 0 ? `(${b})` : b
      return { prompt: `${a} + ${shown} = ?`, answer: a + b, why: `Start at ${a} on the number line and move ${b < 0 ? 'left' : 'right'} ${Math.abs(b)}: ${a + b}.` }
    }
  }
  throw new Error('unknown topic ' + topic)
}

function options(answer, r) {
  const num = Number(String(answer).replace(/ .*/, ''))
  if (typeof answer === 'string' || Number.isNaN(num)) return null
  const step = Number.isInteger(answer) ? 1 : 0.1
  const set = new Set([answer])
  for (const d of [1, -1, 2, 10, -10, 3]) {
    if (set.size >= 4) break
    const v = Math.round((answer + d * step * between(r, 1, 2)) * 10) / 10
    if (v !== answer && (answer < 0 || v >= 0)) set.add(v)
  }
  return [...set].sort(() => r() - 0.5)
}

/** A drill of `count` questions for a grade and topic. The same seed gives the same drill. */
export function drill(grade, topic, count = 10, seed = Date.now()) {
  const r = rng(`${seed}:${topic}:${grade}`)
  const g = gradeNumber(grade)
  return Array.from({ length: count }, (_, n) => {
    const q = question(topic, g, r)
    return { id: `${topic}-${n}`, ...q, answer: String(q.answer), options: options(q.answer, r)?.map(String) || null }
  })
}

/** True when the learner's answer matches, accepting "3 1/2", "7/2" and "3.5" for the same value. */
export function isRight(given, answer) {
  const norm = (v) => String(v ?? '').trim().replace(/^kes\s*/i, '').replace(/,/g, '')
  const a = norm(given), b = norm(answer)
  if (!a) return false
  if (a === b) return true
  const value = (s) => {
    const mixed = s.match(/^(-?\d+)\s+(\d+)\/(\d+)$/)
    if (mixed) return Number(mixed[1]) + Math.sign(Number(mixed[1]) || 1) * (Number(mixed[2]) / Number(mixed[3]))
    const f = s.match(/^(-?\d+)\/(\d+)$/)
    if (f) return Number(f[1]) / Number(f[2])
    return Number(s)
  }
  const x = value(a), y = value(b)
  return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x - y) < 1e-9
}
