import { call } from './tauri.js'
import * as L from './learner.js'

/**
 * Practice that comes back at the right time (spaced repetition), kept on the device so it
 * works offline. Each question from a quiz the learner has taken sits in a box: a right
 * answer moves it up a box and further away, a wrong one sends it back to tomorrow.
 */
const GAPS = [1, 3, 7, 14, 30]
export const PER_DAY = 5

const iso = (d) => d.toISOString().slice(0, 10)
const today = () => iso(new Date())
const plus = (days) => iso(new Date(Date.now() + days * 86400000))

function key(student) {
  return `cbc:review:${student || 'learner'}`
}

function load(student) {
  try {
    return JSON.parse(localStorage.getItem(key(student)) || '{}')
  } catch {
    return {}
  }
}

function save(student, state) {
  try {
    localStorage.setItem(key(student), JSON.stringify(state))
  } catch {
    /* private window: practice still works, it just starts fresh next visit */
  }
}

/** Questions due today, those from the weakest quizzes first, at most `limit`. */
export async function due(student, limit = PER_DAY) {
  const attempts = await L.mine('quiz_attempt')
  const best = {}
  for (const a of attempts) {
    const s = Number(a.score)
    if (a.quiz && !isNaN(s)) best[a.quiz] = Math.max(best[a.quiz] ?? 0, s)
  }
  const state = load(student)
  const out = []
  for (const [quizName, score] of Object.entries(best)) {
    const quiz = await call('local_quiz', { name: quizName }).catch(() => null)
    for (const q of quiz?.question_rows || []) {
      if (q.question_type === 'Multiple Correct Answer' || !q.options?.some((o) => o.is_correct)) continue
      // First time: missed quizzes come back today, a perfect one in a week.
      state[q.name] ??= score >= 100 ? { box: 2, due: plus(7) } : { box: 0, due: today() }
      if (state[q.name].due <= today()) out.push({ ...q, quiz: quizName, quizScore: score, box: state[q.name].box })
    }
  }
  save(student, state)
  out.sort((a, b) => a.box - b.box || a.quizScore - b.quizScore)
  return { questions: out.slice(0, limit), total: out.length }
}

export function mark(student, question, right) {
  const state = load(student)
  const box = right ? Math.min((state[question]?.box ?? 0) + 1, GAPS.length - 1) : 0
  state[question] = { box, due: plus(right ? GAPS[box] : 1) }
  save(student, state)
}
