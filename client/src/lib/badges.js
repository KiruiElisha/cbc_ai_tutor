import * as L from './learner.js'

/**
 * Badges earned from what the learner has done on this device and synced from the server:
 * lessons, quizzes, streaks and practice. Worked out each time, so nothing extra is stored
 * except which ones have been celebrated already.
 */
export const BADGES = [
  ['first-lesson', '🌱', 'First step', 'Finish your first lesson', (s) => s.lessons >= 1],
  ['five-lessons', '📗', 'Bookworm', 'Finish 5 lessons', (s) => s.lessons >= 5],
  ['twenty-lessons', '📚', 'Library', 'Finish 20 lessons', (s) => s.lessons >= 20],
  ['fifty-lessons', '🏛️', 'Scholar', 'Finish 50 lessons', (s) => s.lessons >= 50],
  ['first-quiz', '✏️', 'Quiz taker', 'Take your first quiz', (s) => s.quizzes >= 1],
  ['perfect', '💯', 'Perfect score', 'Get every question right in a quiz', (s) => s.perfect >= 1],
  ['five-perfect', '🏆', 'Champion', 'Get 5 perfect quizzes', (s) => s.perfect >= 5],
  ['streak-3', '🔥', 'On fire', 'Learn 3 days in a row', (s) => s.streak >= 3],
  ['streak-7', '🌟', 'Week star', 'Learn 7 days in a row', (s) => s.streak >= 7],
  ['streak-30', '🦁', 'Simba', 'Learn 30 days in a row', (s) => s.streak >= 30],
  ['explorer', '🧭', 'Explorer', 'Finish lessons in 3 learning areas', (s) => s.areas >= 3],
  ['area-done', '🎓', 'Area master', 'Finish every lesson in a learning area', (s) => s.areasDone >= 1],
]

export async function stats() {
  const [done, attempts, act, areas] = await Promise.all([
    L.progressByLesson(),
    L.mine('quiz_attempt'),
    L.activity(),
    L.list('area'),
  ])
  const finished = new Set(Object.values(done).filter((p) => p.status === 'Completed').map((p) => p.lesson))
  let touched = 0
  let complete = 0
  for (const a of areas) {
    const lessons = await L.list('lesson', a.name)
    const n = lessons.filter((l) => finished.has(l.name)).length
    if (n) touched++
    if (lessons.length && n === lessons.length) complete++
  }
  return {
    lessons: finished.size,
    quizzes: attempts.length,
    perfect: attempts.filter((a) => Number(a.score) >= 100).length,
    streak: act.streak,
    areas: touched,
    areasDone: complete,
  }
}

export async function earned() {
  const s = await stats()
  return BADGES.map(([id, icon, name, how, test]) => ({ id, icon, name, how, got: !!test(s) }))
}

/** Badges earned since the last time this learner was shown them, marked as seen. */
export async function fresh(student) {
  const key = `cbc:badges:${student || 'learner'}`
  let seen = []
  try {
    seen = JSON.parse(localStorage.getItem(key) || '[]')
  } catch {
    /* none seen */
  }
  const got = (await earned()).filter((b) => b.got)
  const now = got.filter((b) => !seen.includes(b.id))
  try {
    localStorage.setItem(key, JSON.stringify(got.map((b) => b.id)))
  } catch {
    /* celebrated again next time, which is harmless */
  }
  // The very first visit marks what was already earned without a fuss.
  return seen.length || !got.length ? now : []
}
