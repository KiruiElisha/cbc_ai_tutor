/**
 * Mark a quiz on the device so the learner sees a result offline. The server marks
 * it again when it syncs; that score is the one that counts.
 * `answers`: { [question]: Set of option ids }
 */
export function markQuiz(questions, answers) {
  let correct = 0
  const rows = questions.map((q) => {
    const right = new Set(q.options.filter((o) => o.is_correct).map((o) => o.id))
    const chosen = answers[q.name] || new Set()
    const ok = right.size > 0 && right.size === chosen.size && [...right].every((id) => chosen.has(id))
    if (ok) correct++
    return { question: q.name, correct: ok, right: [...right] }
  })
  const score = questions.length ? Math.round((correct * 10000) / questions.length) / 100 : 0
  return { score, correct, total: questions.length, rows }
}

export function shuffle(list, seed) {
  const out = [...list]
  let s = [...String(seed)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7)
  for (let i = out.length - 1; i > 0; i--) {
    s = (s * 1103515245 + 12345) >>> 0
    const j = s % (i + 1)
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}
