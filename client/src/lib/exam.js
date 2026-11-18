import { call } from './tauri.js'
import * as L from './learner.js'
import { shuffle } from './quiz.js'

/**
 * Exam practice from the quizzes on the device: a mixed paper across learning areas, timed like
 * the real thing, marked on the device (works offline) with a score for each area. Nothing is
 * sent to the server: it is practice, and the learner's quiz results stay as they are.
 */
export const PER_QUESTION_SECONDS = 72

export function examName(grade) {
  if (grade === 'Grade 6') return 'KPSEA practice'
  if (grade === 'Grade 9') return 'KJSEA practice'
  return 'Exam practice'
}

/** Up to `size` single-answer questions, spread fairly across the learning areas. */
export async function paper(size = 20, seed = Date.now()) {
  const byArea = {}
  for (const area of await L.list('area')) {
    for (const lesson of await L.list('lesson', area.name)) {
      if (!lesson.quiz || lesson.locked) continue
      const quiz = await call('local_quiz', { name: lesson.quiz }).catch(() => null)
      for (const q of quiz?.question_rows || []) {
        if (q.question_type === 'Multiple Correct Answer' || !q.options?.some((o) => o.is_correct)) continue
        ;(byArea[area.title] ||= []).push({ ...q, area: area.title, options: shuffle(q.options, q.name + seed) })
      }
    }
  }
  const pools = Object.values(byArea).map((qs) => shuffle(qs, seed))
  const out = []
  // One from each area in turn, so no area takes over the paper.
  while (out.length < size && pools.some((p) => p.length)) {
    for (const pool of pools) if (pool.length && out.length < size) out.push(pool.shift())
  }
  return shuffle(out, seed + 'order')
}

export function mark(questions, chosen) {
  const areas = {}
  let right = 0
  for (const q of questions) {
    const ok = !!q.options.find((o) => o.id === chosen[q.name])?.is_correct
    if (ok) right++
    const a = (areas[q.area] ||= { area: q.area, right: 0, total: 0 })
    a.total++
    if (ok) a.right++
  }
  return {
    right,
    total: questions.length,
    score: questions.length ? Math.round((100 * right) / questions.length) : 0,
    areas: Object.values(areas).sort((a, b) => a.right / a.total - b.right / b.total),
  }
}
