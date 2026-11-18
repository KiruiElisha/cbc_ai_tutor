import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

export function safeHtml(html) {
  return DOMPurify.sanitize(html || '', {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'target'],
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|tel:|data:image\/|#|\/)/i,
  })
}

export function markdown(text) {
  return safeHtml(marked.parse(text || ''))
}

/**
 * Mwalimu's reply as HTML laid out for learning: the line that starts with **Answer:** (or
 * **Jibu:**) becomes an answer box. Numbered steps are styled as cards in app.css.
 */
export function tutorHtml(text) {
  return markdown(text).replace(/<p>(<strong>(?:Answer|Jibu|Final answer)\s*:?\s*<\/strong>)/gi, '<p class="answer-box">$1')
}

export function plain(html) {
  const div = document.createElement('div')
  div.innerHTML = DOMPurify.sanitize(html || '')
  return (div.textContent || '').trim()
}

const parse = (v) => (v ? new Date(String(v).replace(' ', 'T')) : null)

export function date(v) {
  const d = parse(v)
  return d && !isNaN(d) ? d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' }) : ''
}

export function dateTime(v) {
  const d = parse(v)
  return d && !isNaN(d)
    ? d.toLocaleString('en-KE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    : ''
}

export function ago(v) {
  const d = parse(v)
  if (!d || isNaN(d)) return 'never'
  const s = (Date.now() - d.getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return date(v)
}

export function kes(n) {
  return 'KES ' + Number(n || 0).toLocaleString('en-KE', { maximumFractionDigits: 0 })
}

/** A KES amount in US dollars at `rate` KES to the dollar, as a guide ("≈ US$3.87"). */
export function usd(kesAmount, rate) {
  if (!rate || !kesAmount) return ''
  const dollars = Number(kesAmount) / Number(rate)
  return '≈ US$' + dollars.toLocaleString('en-US', { minimumFractionDigits: dollars < 100 ? 2 : 0, maximumFractionDigits: 2 })
}

export function money(n, currency) {
  return `${currency} ${Number(n || 0).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function minutes(seconds) {
  const m = Math.round((seconds || 0) / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
}

export function nowString() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() || '')
    .join('')
}

/** CBC rubric wording for a percentage score. */
export function level(score) {
  if (score == null) return ''
  if (score >= 80) return 'Exceeding expectations'
  if (score >= 60) return 'Meeting expectations'
  if (score >= 40) return 'Approaching expectations'
  return 'Below expectations'
}
