import { invoke } from '@tauri-apps/api/core'

/** Errors from Rust arrive as { kind, status, message, exc_type }. */
export function errorText(e, fallback = 'Something went wrong. Try again.') {
  if (!e) return fallback
  if (typeof e === 'string') return e
  return e.message || fallback
}

export function isOffline(e) {
  return e?.kind === 'offline'
}

export function needsPlan(e) {
  return e?.kind === 'subscription_required'
}

export const call = (cmd, args) => invoke(cmd, args)

/**
 * A server API method under `cbc_ai_tutor.api.` (e.g. 'parent.dashboard').
 * With `cache`, an offline device gets the last answer back with `cached: true`.
 */
export async function api(path, args = {}, { method = 'POST', cache = null, guest = false } = {}) {
  const res = await invoke('api', { method, path, args, cacheKey: cache, guest })
  return cache ? res : res.data
}

export const get = (path, args = {}, opts = {}) => api(path, args, { ...opts, method: 'GET' })

export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('Could not read the file.'))
    reader.readAsDataURL(file)
  })
}

export function base64ToBlobUrl(b64, filename) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  const ext = (filename.split('.').pop() || '').toLowerCase()
  const types = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', txt: 'text/plain', mp3: 'audio/mpeg', m4a: 'audio/mp4' }
  return URL.createObjectURL(new Blob([bytes], { type: types[ext] || 'application/octet-stream' }))
}
