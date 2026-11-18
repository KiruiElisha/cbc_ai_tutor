/**
 * The parent PIN on this device: needed to leave learner mode, so a child handed the phone
 * can't wander into payments or other children's progress. Only a salted hash is kept. A
 * forgotten PIN is cleared by signing in again as the parent.
 */
const KEY = 'cbc:parent_pin'

async function hash(pin) {
  const bytes = new TextEncoder().encode('cbc-parent-pin:' + pin)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

function stored() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export const hasPin = () => !!stored()

export async function setPin(pin) {
  try {
    localStorage.setItem(KEY, await hash(pin))
  } catch {
    /* private window: the device just has no PIN */
  }
}

export async function checkPin(pin) {
  const want = stored()
  return !want || want === (await hash(pin))
}

export function clearPin() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing to clear */
  }
}
