import { call } from './tauri.js'

/** Local lookups shared by the learner screens. Everything here works offline. */

export const status = () => call('learner_status')
export const list = (kind, parent = null) => call('local_list', { kind, parent })
export const one = (kind, name) => call('local_get', { kind, name })
export const mine = (kind) => call('mine_list', { kind })

export async function progressByLesson() {
  const rows = await mine('lesson_progress')
  return Object.fromEntries(rows.map((r) => [r.lesson, r]))
}

export async function bestScores() {
  const best = {}
  for (const a of await mine('quiz_attempt')) {
    const s = Number(a.score)
    if (a.quiz && !isNaN(s)) best[a.quiz] = Math.max(best[a.quiz] ?? 0, s)
  }
  return best
}

/** Server file paths ('/files/x.png') work from the app only as full URLs. */
export function absolutize(html, server) {
  if (!html || !server) return html || ''
  return html.replace(/(src|href)=("|')\/(files|private\/files|assets)\//g, `$1=$2${server}/$3/`)
}

export function fileUrl(path, server) {
  if (!path) return ''
  return /^https?:/.test(path) ? path : server + path
}

export function videoEmbed(url) {
  if (!url) return null
  const yt = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{11})/)
  if (yt) return `https://www.youtube-nocookie.com/embed/${yt[1]}`
  const vimeo = url.match(/vimeo\.com\/(\d+)/)
  if (vimeo) return `https://player.vimeo.com/video/${vimeo[1]}`
  return null
}

const day = (v) => String(v || '').slice(0, 10)

/** Days in a row with learning done, counting today or, until it is done, yesterday. */
export function streak(dates, today = new Date()) {
  const days = new Set(dates.map(day).filter(Boolean))
  const iso = (d) => d.toISOString().slice(0, 10)
  const cursor = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()))
  if (!days.has(iso(cursor))) cursor.setUTCDate(cursor.getUTCDate() - 1)
  let n = 0
  while (days.has(iso(cursor))) {
    n++
    cursor.setUTCDate(cursor.getUTCDate() - 1)
  }
  return n
}

/** Streak and today's goal (lessons opened plus quizzes taken today, out of 3). */
export async function activity(goal = 3) {
  const [lessons, quizzes] = await Promise.all([mine('lesson_progress'), mine('quiz_attempt')])
  const dates = [...lessons.map((r) => r.last_opened), ...quizzes.map((r) => r.created || r.date)]
  const today = new Date().toISOString().slice(0, 10)
  const done = dates.filter((d) => day(d) === today).length
  return { streak: streak(dates), today: Math.min(done, goal), goal }
}
