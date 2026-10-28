import { call, errorText, isOffline } from './tauri.js'

/** App-wide state: who is signed in, connection, sync, messages. */
export const app = $state({
  ready: false,
  server: '',
  session: null,
  parentWaiting: false,
  online: navigator.onLine,
  pending: 0,
  lastSync: null,
  syncing: false,
  syncError: '',
  version: '',
  platform: '',
})

export const toasts = $state([])

export function toast(message, tone = 'info') {
  const id = Math.random().toString(36).slice(2)
  toasts.push({ id, message, tone })
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id)
    if (i >= 0) toasts.splice(i, 1)
  }, tone === 'error' ? 6000 : 3500)
}

export async function refreshState() {
  const s = await call('app_state')
  app.server = s.server
  app.session = s.session
  app.parentWaiting = s.parent_waiting
  app.pending = s.pending
  app.lastSync = s.last_sync
  app.version = s.version
  app.platform = s.platform
  app.ready = true
  return s
}

export const role = () => app.session?.role || null
export const profile = () => app.session?.profile || {}

let syncTimer = null

/** Push queued work and pull new lessons. Quiet when offline. */
export async function syncNow({ quiet = false } = {}) {
  if (app.session?.role !== 'Learner' || app.syncing) return null
  app.syncing = true
  try {
    const report = await call('sync_now')
    app.pending = report.pending
    app.lastSync = report.last_sync
    app.syncError = ''
    app.online = true
    if (!quiet && report.rejected) toast(`${report.rejected} item(s) were not accepted. See Sync.`, 'error')
    window.dispatchEvent(new CustomEvent('cbc:synced', { detail: report }))
    return report
  } catch (e) {
    if (isOffline(e)) {
      app.online = false
      app.syncError = ''
      if (!quiet) toast('You are offline. Your work is saved and will send later.')
    } else if (e?.kind === 'signed_out') {
      await refreshState()
    } else {
      app.syncError = errorText(e)
      if (!quiet) toast(app.syncError, 'error')
    }
    return null
  } finally {
    app.syncing = false
  }
}

export function startAutoSync() {
  stopAutoSync()
  syncTimer = setInterval(() => syncNow({ quiet: true }), 5 * 60 * 1000)
}

export function stopAutoSync() {
  if (syncTimer) clearInterval(syncTimer)
  syncTimer = null
}

window.addEventListener('online', () => {
  app.online = true
  syncNow({ quiet: true })
})
window.addEventListener('offline', () => (app.online = false))

export async function queue(kind, payload) {
  const res = await call('queue_event', { kind, payload })
  app.pending = res.pending
  if (app.online) setTimeout(() => syncNow({ quiet: true }), 300)
  return res
}
