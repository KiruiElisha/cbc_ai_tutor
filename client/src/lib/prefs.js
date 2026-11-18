/**
 * How this device shows the app: light or dark, text size and language. Kept on the device
 * (a phone shared by siblings keeps one setting) and applied before the first screen draws.
 */
const KEY = 'cbc:prefs'
const DEFAULTS = { theme: 'auto', text: 'normal', lang: 'en' }

export function prefs() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }
  } catch {
    return { ...DEFAULTS }
  }
}

export function apply(p = prefs()) {
  const root = document.documentElement
  if (p.theme === 'auto') delete root.dataset.theme
  else root.dataset.theme = p.theme
  root.dataset.text = p.text
  root.lang = p.lang === 'sw' ? 'sw' : 'en'
}

export function setPref(name, value) {
  const p = { ...prefs(), [name]: value }
  try {
    localStorage.setItem(KEY, JSON.stringify(p))
  } catch {
    /* private window: the setting lasts this visit */
  }
  apply(p)
  window.dispatchEvent(new CustomEvent('cbc:prefs', { detail: p }))
  return p
}
