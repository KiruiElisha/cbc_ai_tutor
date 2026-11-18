/**
 * Talking to Mwalimu with the device's own speech engines: nothing to download, and nothing
 * leaves the device except through the engine the device already uses.
 *
 * - Listening uses SpeechRecognition (Chrome, Edge, Android WebView and Safari have it; some
 *   desktop WebViews do not, and the mic button is then hidden).
 * - Reading aloud uses speechSynthesis, which every supported platform has.
 */

const Recognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null

export const canListen = !!Recognition
export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

/** Kiswahili words common enough that a reply with several of them is Kiswahili. */
const SWAHILI = /\b(na|ya|wa|kwa|ni|za|katika|hii|hiyo|kuwa|sana|pia|lakini|jibu|swali|habari|mwalimu|nieleze|tafadhali)\b/gi

export function looksSwahili(text) {
  const words = (text || '').split(/\s+/).length || 1
  return (text.match(SWAHILI) || []).length / words > 0.12
}

/**
 * Listen once. `onText(text, final)` gets the words as they are heard; the returned function
 * stops listening. `lang` is a BCP 47 tag such as 'en-KE' or 'sw-KE'.
 */
export function listen({ lang = 'en-KE', onText, onEnd, onError }) {
  if (!Recognition) {
    onError?.('Voice typing is not available on this device.')
    return () => {}
  }
  const rec = new Recognition()
  rec.lang = lang
  rec.interimResults = true
  rec.continuous = false
  rec.maxAlternatives = 1
  rec.onresult = (e) => {
    let text = ''
    let final = false
    for (const result of e.results) {
      text += result[0].transcript
      final = result.isFinal
    }
    onText?.(text.trim(), final)
  }
  rec.onerror = (e) => {
    const reason = {
      'not-allowed': 'Allow the microphone for this app to speak your question.',
      'service-not-allowed': 'Allow the microphone for this app to speak your question.',
      'no-speech': "I didn't hear anything. Tap the mic and speak.",
      network: 'Voice typing needs the internet on this device.',
    }[e.error]
    if (e.error !== 'aborted') onError?.(reason || 'Voice typing stopped. Try again.')
  }
  rec.onend = () => onEnd?.()
  try {
    rec.start()
  } catch {
    onError?.('Voice typing could not start. Try again.')
  }
  return () => {
    try {
      rec.stop()
    } catch {
      /* already stopped */
    }
  }
}

/** What a reply sounds like read out: no Markdown marks, links read by their words. */
export function speechText(markdown) {
  return (markdown || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/[*_`>|#]/g, '')
    .replace(/(\d)\s*\/\s*(\d)/g, '$1 over $2')
    .replace(/\s+/g, ' ')
    .trim()
}

function voiceFor(lang) {
  const voices = window.speechSynthesis.getVoices()
  const base = lang.split('-')[0]
  return voices.find((v) => v.lang === lang) || voices.find((v) => v.lang?.startsWith(base)) || null
}

/** Read text aloud, stopping anything already being read. Resolves when it has finished. */
export function speak(text, { lang } = {}) {
  if (!canSpeak) return Promise.resolve()
  const synth = window.speechSynthesis
  synth.cancel()
  const spoken = speechText(text)
  if (!spoken) return Promise.resolve()
  const tag = lang || (looksSwahili(spoken) ? 'sw-KE' : 'en-KE')
  const utterance = new SpeechSynthesisUtterance(spoken)
  utterance.lang = tag
  utterance.voice = voiceFor(tag) || voiceFor('en-GB')
  utterance.rate = 0.95
  return new Promise((resolve) => {
    utterance.onend = resolve
    utterance.onerror = resolve
    synth.speak(utterance)
  })
}

export function stopSpeaking() {
  if (canSpeak) window.speechSynthesis.cancel()
}

/**
 * Read text aloud word by word for read-along: `onWord(i)` gets the index of the word being
 * said (in `text.split(/\s+/)`), so the screen can light it up. Resolves when done or stopped.
 */
export function readAlong(text, { lang, onWord } = {}) {
  if (!canSpeak) return Promise.resolve()
  const synth = window.speechSynthesis
  synth.cancel()
  const words = text.split(/\s+/).filter(Boolean)
  const starts = []
  let at = 0
  const joined = words.join(' ')
  for (const w of words) {
    starts.push(at)
    at += w.length + 1
  }
  const tag = lang || (looksSwahili(joined) ? 'sw-KE' : 'en-KE')
  const u = new SpeechSynthesisUtterance(joined)
  u.lang = tag
  u.voice = voiceFor(tag) || voiceFor('en-GB')
  u.rate = 0.85
  u.onboundary = (e) => {
    if (e.name && e.name !== 'word') return
    let i = starts.length - 1
    while (i > 0 && starts[i] > e.charIndex) i--
    onWord?.(i)
  }
  return new Promise((resolve) => {
    u.onend = () => {
      onWord?.(-1)
      resolve()
    }
    u.onerror = u.onend
    synth.speak(u)
  })
}
