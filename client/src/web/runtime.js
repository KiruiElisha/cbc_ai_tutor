/**
 * The web (PWA) build's stand-in for the Rust side: the same commands the desktop and mobile
 * apps answer in src-tauri/src/commands.rs, answered in the browser.
 *
 * - The server is the site the page came from; calls carry the device token as a Bearer header
 *   and never cookies, so a Desk session in the same browser can't leak into the app.
 * - Lessons, quizzes and the learner's own records live in IndexedDB, so a learner can keep
 *   reading and taking quizzes offline. Work done offline waits in the outbox and is sent on the
 *   next sync, exactly as in the apps (sync.push / sync.pull).
 * - Tokens are kept in localStorage, as the Android and Linux apps keep theirs in their own
 *   store. "Remove everything from this device" deletes them with the offline data.
 */

const METHOD = '/api/method/cbc_ai_tutor.api.'
const TOKEN_ENDPOINTS = new Set([
  'auth.login', 'auth.learner_login', 'auth.signup_parent', 'auth.open_learner', 'signin.confirm_email_code', 'signin.exchange',
])
const EVENT_KINDS = ['lesson_progress', 'quiz_attempt', 'assignment_submission', 'practice_answers', 'ai_feedback']
const CONTENT = [
  ['strands', 'strand', 'course'],
  ['sub_strands', 'sub_strand', 'strand'],
  ['outcomes', 'outcome', 'sub_strand'],
  ['lessons', 'lesson', 'course'],
  ['quizzes', 'quiz', ''],
  ['questions', 'question', ''],
]
const KIND_FOR_DOCTYPE = { Lesson: 'lesson', Strand: 'strand', 'Sub-strand': 'sub_strand', 'Learning Outcome': 'outcome', Quiz: 'quiz', Question: 'question' }
const BATCH = 100
const MAX_ATTEMPTS = 8
const VERSION = import.meta.env.VITE_APP_VERSION || 'web'

class AppError extends Error {
  constructor(kind, message, extra = {}) {
    super(message)
    Object.assign(this, { kind, message, ...extra })
  }
}
const offline = (m = 'No connection to the server.') => new AppError('offline', m)
const signedOut = (m = 'Please sign in.') => new AppError('signed_out', m)
const invalid = (m) => new AppError('invalid', m)

const now = () => new Date().toISOString().replace('T', ' ').slice(0, 19)
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`)

// --- IndexedDB -------------------------------------------------------------------------------

let dbp = null
function db() {
  if (dbp) return dbp
  dbp = new Promise((resolve, reject) => {
    const req = indexedDB.open('cbc-tutor', 1)
    req.onupgradeneeded = () => {
      const d = req.result
      const content = d.createObjectStore('content', { keyPath: ['scope', 'kind', 'name'] })
      content.createIndex('by_kind', ['scope', 'kind'])
      content.createIndex('by_parent', ['scope', 'kind', 'parent'])
      const mine = d.createObjectStore('mine', { keyPath: ['scope', 'kind', 'key'] })
      mine.createIndex('by_kind', ['scope', 'kind'])
      const outbox = d.createObjectStore('outbox', { keyPath: 'uuid' })
      outbox.createIndex('by_scope', 'scope')
      d.createObjectStore('kv')
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(new AppError('storage', 'This browser could not open its offline storage.'))
  })
  return dbp
}

const done = (req) => new Promise((resolve, reject) => {
  req.onsuccess = () => resolve(req.result)
  req.onerror = () => reject(req.error)
})

async function tx(stores, mode, fn) {
  const t = (await db()).transaction(stores, mode)
  const out = await fn(Object.fromEntries([].concat(stores).map((s) => [s, t.objectStore(s)])))
  await new Promise((resolve, reject) => {
    t.oncomplete = resolve
    t.onerror = () => reject(t.error)
    t.onabort = () => reject(t.error)
  })
  return out
}

const kvGet = (key) => tx('kv', 'readonly', (s) => done(s.kv.get(key)))
const kvSet = (key, value) => tx('kv', 'readwrite', (s) => s.kv.put(value, key))
const kvJson = async (key) => {
  const raw = await kvGet(key)
  try {
    return raw == null ? null : JSON.parse(raw)
  } catch {
    return null
  }
}

const bySort = (a, b) => (a.sort - b.sort) || String(a.name).localeCompare(String(b.name))

async function contentList(scope, kind, parent) {
  return tx('content', 'readonly', async (s) => {
    const rows = parent
      ? await done(s.content.index('by_parent').getAll([scope, kind, parent]))
      : await done(s.content.index('by_kind').getAll([scope, kind]))
    return rows.sort(bySort).map((r) => r.data)
  })
}
const contentGet = (scope, kind, name) =>
  tx('content', 'readonly', async (s) => (await done(s.content.get([scope, kind, name])))?.data ?? null)
const contentCount = (scope, kind) => tx('content', 'readonly', (s) => done(s.content.index('by_kind').count([scope, kind])))

const mineGet = (scope, kind, key) =>
  tx('mine', 'readonly', async (s) => (await done(s.mine.get([scope, kind, key])))?.data ?? null)
const minePut = (scope, kind, key, data, local) =>
  tx('mine', 'readwrite', (s) => s.mine.put({ scope, kind, key, data, local: local ? 1 : 0, updated: Date.now() }))
async function mineList(scope, kind) {
  const rows = await tx('mine', 'readonly', (s) => done(s.mine.index('by_kind').getAll([scope, kind])))
  return rows.sort((a, b) => b.updated - a.updated).map((r) => ({ ...r.data, _local: r.local }))
}

const outboxAll = (scope) => tx('outbox', 'readonly', (s) => done(s.outbox.index('by_scope').getAll(scope)))
async function outboxPending(scope, limit) {
  const rows = (await outboxAll(scope)).filter((r) => r.state === 'pending' && (!r.retry_after || r.retry_after <= Date.now()))
  return rows.sort((a, b) => a.created - b.created).slice(0, limit)
}
const outboxCount = async (scope) => (await outboxAll(scope)).filter((r) => r.state === 'pending').length
const outboxUpdate = (id, change) =>
  tx('outbox', 'readwrite', async (s) => {
    const row = await done(s.outbox.get(id))
    if (row) s.outbox.put({ ...row, ...change })
  })
const outboxDone = (id) => tx('outbox', 'readwrite', (s) => s.outbox.delete(id))

// --- sessions ----------------------------------------------------------------------------------

const PARENT = 'parent'
const ACTIVE = 'active'
function loadSession(slot) {
  try {
    return JSON.parse(localStorage.getItem(`cbc:session:${slot}`) || 'null')
  } catch {
    return null
  }
}
function saveSession(slot, session) {
  if (session) localStorage.setItem(`cbc:session:${slot}`, JSON.stringify(session))
  else localStorage.removeItem(`cbc:session:${slot}`)
}
let active = loadSession(ACTIVE)

function fromLogin(resp) {
  if (!resp?.token) throw invalid('The server did not return a session.')
  const profile = resp.profile || null
  return { token: resp.token, role: resp.role || '', user: profile?.user || '', student: profile?.learner?.student || null, profile }
}
const scopeOf = (s) => (s && s.role === 'Learner' ? s.student : null)
const publicSession = (s) => (s ? { role: s.role, user: s.user, student: s.student, profile: s.profile } : null)
function setActive(s) {
  active = s
  saveSession(ACTIVE, s)
}
function needActive() {
  if (!active) throw signedOut()
  return active
}
function learnerScope() {
  const scope = scopeOf(needActive())
  if (!scope) throw invalid('Open a learner profile first.')
  return scope
}

function deviceArgs() {
  const ua = navigator.userAgent
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser'
  const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : ''
  return { device_name: `${browser}${os ? ' on ' + os : ''} (web)`, platform: 'web', app_version: VERSION }
}

// --- the server --------------------------------------------------------------------------------

function strip(s) {
  return String(s || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim()
}
function serverMessage(body) {
  try {
    const list = JSON.parse(body?._server_messages || '[]')
    for (const item of list.reverse()) {
      let msg = item
      try {
        msg = JSON.parse(item).message || item
      } catch { /* plain text */ }
      if (strip(msg)) return strip(msg)
    }
  } catch { /* not a list */ }
  if (typeof body?.exception === 'string') return strip(body.exception.split(': ').slice(1).join(': ') || body.exception)
  return typeof body?.message === 'string' ? strip(body.message) : null
}

async function request(httpMethod, path, args = {}, token = null) {
  if (!/^[A-Za-z0-9._]+$/.test(path)) throw invalid('Bad API path.')
  let url = METHOD + path
  const init = { method: httpMethod, credentials: 'omit', headers: { Accept: 'application/json' } }
  if (httpMethod === 'GET') {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(args || {})) {
      if (v === null || v === undefined) continue
      q.set(k, typeof v === 'boolean' ? (v ? '1' : '0') : typeof v === 'object' ? JSON.stringify(v) : String(v))
    }
    if ([...q].length) url += '?' + q
  } else {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(args || {})
  }
  if (token) init.headers.Authorization = `Bearer ${token}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 90000)
  let resp
  try {
    resp = await fetch(url, { ...init, signal: ctrl.signal })
  } catch (e) {
    throw offline(e?.name === 'AbortError' ? 'The server took too long to answer.' : 'No connection to the server.')
  } finally {
    clearTimeout(timer)
  }
  let body = null
  try {
    body = await resp.json()
  } catch { /* not JSON */ }
  if (resp.ok) return body?.message ?? null
  const status = resp.status
  const message = serverMessage(body) || ({ 401: 'Please sign in again.', 404: 'The server does not have this feature.' }[status]
    || (status >= 502 && status <= 504 ? 'The server is not reachable right now.' : `The server could not do that (error ${status}).`))
  if (status === 401) throw signedOut(message)
  if (status === 402 || body?.exc_type === 'SubscriptionRequired') throw new AppError('subscription_required', message, { status })
  throw new AppError('server', message, { status, exc_type: body?.exc_type })
}

async function signIn(path, args) {
  const resp = await request('POST', path, { ...args, ...deviceArgs() })
  const s = fromLogin(resp)
  saveSession(PARENT, null)
  setActive(s)
  return publicSession(s)
}

async function signedInOrPending(resp) {
  if (resp?.needs_profile) return resp
  const s = fromLogin(resp)
  saveSession(PARENT, null)
  setActive(s)
  return publicSession(s)
}

// --- sync (src-tauri/src/sync.rs) -------------------------------------------------------------

let syncing = null

async function queue(scope, kind, payload) {
  if (!EVENT_KINDS.includes(kind)) throw invalid(`Unknown event ${kind}.`)
  if (typeof payload?.attachment_data === 'string' && payload.attachment_data.length > 11 * 1024 * 1024) {
    throw invalid('Files can be up to 8 MB.')
  }
  const id = uuid()
  await tx('outbox', 'readwrite', (s) =>
    s.outbox.put({ uuid: id, scope, type: kind, payload, at: now(), created: Date.now(), attempts: 0, state: 'pending', error: null }))
  if (kind === 'lesson_progress') {
    const lesson = payload.lesson
    const row = (await mineGet(scope, 'lesson_progress', lesson)) || { lesson, status: 'Started', progress: 0, time_spent: 0 }
    const progress = Number(payload.progress) || 0
    const completed = Number(payload.completed) === 1 || progress >= 100
    row.progress = completed ? 100 : Math.max(Number(row.progress) || 0, progress)
    row.time_spent = (Number(row.time_spent) || 0) + Math.max(0, Number(payload.time_spent_delta) || 0)
    row.last_opened = now()
    if (completed) {
      row.status = 'Completed'
      row.completed_on = row.completed_on || now()
    }
    await minePut(scope, 'lesson_progress', lesson, row, true)
  } else if (kind === 'quiz_attempt') {
    await minePut(scope, 'quiz_attempt', id, {
      client_uuid: id, quiz: payload.quiz, lesson: payload.lesson, score: payload.score, status: 'Waiting to send', time_completed: now(),
    }, true)
  } else if (kind === 'assignment_submission') {
    await minePut(scope, 'submission', payload.assignment, {
      assignment: payload.assignment, client_uuid: id, status: 'Waiting to send', answer_text: payload.answer_text,
      attachment_name: payload.attachment_name, submission_date: now(),
    }, true)
  }
  return { uuid: id, pending: await outboxCount(scope) }
}

async function markRejected(scope, row, message) {
  const [kind, key] = row.type === 'quiz_attempt' ? ['quiz_attempt', row.uuid]
    : row.type === 'assignment_submission' ? ['submission', row.payload?.assignment] : [null, null]
  if (!kind) return
  const data = await mineGet(scope, kind, key)
  if (data) await minePut(scope, kind, key, { ...data, status: 'Not accepted', sync_error: message }, true)
}

async function applyResult(scope, row, result) {
  if (row.type === 'quiz_attempt') {
    const data = (await mineGet(scope, 'quiz_attempt', row.uuid)) || {}
    for (const k of ['name', 'score', 'status', 'attempt_number', 'answers']) if (result?.[k] !== undefined) data[k] = result[k]
    data.client_uuid = row.uuid
    await minePut(scope, 'quiz_attempt', row.uuid, data, false)
  } else if (row.type === 'assignment_submission') {
    const key = row.payload?.assignment
    const data = await mineGet(scope, 'submission', key)
    if (data) await minePut(scope, 'submission', key, { ...data, ...(result?.status ? { status: result.status } : {}), ...(result?.name ? { name: result.name } : {}) }, false)
  }
}

async function push(scope, token) {
  let pushed = 0
  let rejected = 0
  for (let round = 0; round < 10; round++) {
    const rows = await outboxPending(scope, BATCH)
    if (!rows.length) break
    const events = []
    for (const row of rows) {
      const payload = { ...row.payload }
      if (row.type === 'assignment_submission' && payload.attachment_data) {
        try {
          const up = await request('POST', 'sync.upload', { filename: payload.attachment_name || 'work.jpg', content: payload.attachment_data }, token)
          delete payload.attachment_data
          payload.attachment = up?.file_url || ''
          await outboxUpdate(row.uuid, { payload })
        } catch (e) {
          if (e.kind !== 'server') throw e
          await outboxUpdate(row.uuid, { state: 'rejected', error: e.message })
          await markRejected(scope, row, e.message)
          rejected++
          continue
        }
      }
      events.push({ uuid: row.uuid, type: row.type, at: row.at, payload })
    }
    if (!events.length) continue
    const resp = await request('POST', 'sync.push', { events }, token)
    for (const result of resp?.results || []) {
      const row = rows.find((r) => r.uuid === result.uuid)
      if (!row) continue
      if (Number(result.ok) === 1) {
        await applyResult(scope, row, result.result)
        await outboxDone(row.uuid)
        pushed++
      } else {
        const message = result.message || result.error || 'rejected'
        if (Number(result.retry) === 1 && row.attempts + 1 < MAX_ATTEMPTS) {
          await outboxUpdate(row.uuid, { attempts: row.attempts + 1, error: message, retry_after: Date.now() + 60000 * (row.attempts + 1) })
        } else {
          await outboxUpdate(row.uuid, { state: 'rejected', error: message })
          await markRejected(scope, row, message)
          rejected++
        }
      }
    }
    if (rows.length < BATCH) break
  }
  return { pushed, rejected }
}

async function pull(scope, token) {
  const since = await kvGet(`cursor:${scope}`)
  const args = {}
  if (since) {
    args.since = since
    const grade = await kvGet(`grade:${scope}`)
    const entitled = await kvGet(`entitled:${scope}`)
    if (grade) args.grade = grade
    if (entitled != null) args.entitled = entitled
  }
  const data = await request('GET', 'sync.pull', args, token)
  const pending = new Set((await outboxPending(scope, 1000)).filter((r) => r.type === 'lesson_progress').map((r) => r.payload?.lesson))
  const full = Number(data?.full) === 1
  let changes = 0
  await tx(['content', 'mine', 'kv'], 'readwrite', async (s) => {
    const dropWhere = async (store, index, key, keep) => {
      const rows = await done(s[store].index(index).getAll(key))
      for (const r of rows) if (!keep || !keep(r)) s[store].delete(store === 'content' ? [r.scope, r.kind, r.name] : [r.scope, r.kind, r.key])
    }
    const put = (kind, row, parent) => {
      if (!row?.name) return
      s.content.put({ scope, kind, name: row.name, parent: parent ?? null, sort: Number(row.order) || 0, data: row })
    }
    const mput = (kind, key, row) => s.mine.put({ scope, kind, key, data: row, local: 0, updated: Date.now() })
    if (full) {
      const all = await done(s.content.getAll())
      for (const r of all) if (r.scope === scope) s.content.delete([r.scope, r.kind, r.name])
      const mine = await done(s.mine.getAll())
      for (const r of mine) if (r.scope === scope && !r.local) s.mine.delete([r.scope, r.kind, r.key])
    }
    await dropWhere('content', 'by_kind', [scope, 'area'])
    for (const area of data?.learning_areas || []) put('area', area, null)
    for (const [key, kind, parentField] of CONTENT) {
      for (const row of data?.[key] || []) {
        put(kind, row, parentField ? row[parentField] : null)
        changes++
      }
    }
    for (const [doctype, names] of Object.entries(data?.deleted || {})) {
      const kind = KIND_FOR_DOCTYPE[doctype]
      if (!kind) continue
      for (const name of names || []) {
        s.content.delete([scope, kind, name])
        changes++
      }
    }
    const mine = data?.mine || {}
    for (const row of mine.lesson_progress || []) if (!pending.has(row.lesson)) mput('lesson_progress', row.lesson, row)
    for (const row of mine.quiz_attempts || []) mput('quiz_attempt', row.client_uuid || row.name, row)
    if (full) await dropWhere('mine', 'by_kind', [scope, 'assignment'])
    for (const row of mine.assignments || []) mput('assignment', row.name, row)
    for (const row of mine.submissions || []) mput('submission', row.assignment, row)
    for (const row of mine.competencies || []) mput('competency', row.name, row)
    const set = (k, v) => s.kv.put(v, k)
    if (data?.cursor) set(`cursor:${scope}`, data.cursor)
    if (data?.learner?.grade) set(`grade:${scope}`, data.learner.grade)
    set(`entitled:${scope}`, String(Number(data?.entitlement?.active) || 0))
    set(`learner:${scope}`, JSON.stringify(data?.learner ?? null))
    set(`entitlement:${scope}`, JSON.stringify(data?.entitlement ?? null))
    if (mine.ai_quota) set(`ai_quota:${scope}`, JSON.stringify(mine.ai_quota))
  })
  return { full, changes }
}

async function syncNow() {
  if (syncing) return syncing
  syncing = (async () => {
    const s = needActive()
    const scope = scopeOf(s)
    if (!scope) throw invalid('Only learner profiles sync lessons.')
    const { pushed, rejected } = await push(scope, s.token)
    const pulled = await pull(scope, s.token)
    const at = now()
    await kvSet(`last_sync:${scope}`, at)
    return { pushed, rejected, full: pulled.full, changes: pulled.changes, pending: await outboxCount(scope), last_sync: at }
  })()
  try {
    return await syncing
  } catch (e) {
    if (e.kind === 'signed_out') setActive(null)
    throw e
  } finally {
    syncing = null
  }
}

// --- commands (src-tauri/src/commands.rs) -----------------------------------------------------

async function logoutAll() {
  for (const s of [active, loadSession(PARENT)]) {
    if (s) await request('POST', 'auth.logout', {}, s.token).catch(() => {})
  }
  saveSession(PARENT, null)
  setActive(null)
}

const commands = {
  async app_state() {
    const scope = scopeOf(active)
    return {
      server: location.origin,
      session: publicSession(active),
      parent_waiting: !!loadSession(PARENT),
      pending: scope ? await outboxCount(scope) : 0,
      last_sync: scope ? await kvGet(`last_sync:${scope}`) : null,
      version: VERSION,
      platform: 'web',
    }
  },
  login: ({ login, password, role }) => signIn('auth.login', { login, password, role }),
  learner_login: ({ code, pin }) => signIn('auth.learner_login', { code, pin }),
  request_email_code: ({ email, role }) => request('POST', 'signin.request_email_code', { email, role }),
  async confirm_email_code({ email, code, role, fullName, phone }) {
    const args = { email, code, role, ...deviceArgs() }
    if (fullName?.trim()) args.full_name = fullName
    if (phone?.trim()) args.phone = phone
    return signedInOrPending(await request('POST', 'signin.confirm_email_code', args))
  },
  google_signin_url: ({ role }) => request('GET', 'signin.google_url', { role, ...deviceArgs() }),
  async finish_signin({ code }) {
    return signedInOrPending(await request('POST', 'signin.exchange', { code }))
  },
  signup_parent: ({ fullName, email, phone, password }) =>
    signIn('auth.signup_parent', { full_name: fullName, email, phone, password }),
  async open_learner({ student }) {
    const parent = needActive()
    if (parent.role !== 'Parent') throw invalid('Only a parent can open a learner profile.')
    const learner = fromLogin(await request('POST', 'auth.open_learner', { student, ...deviceArgs() }, parent.token))
    saveSession(PARENT, parent)
    setActive(learner)
    return publicSession(learner)
  },
  async back_to_parent() {
    const parent = loadSession(PARENT)
    if (!parent) throw signedOut('Sign in as the parent again.')
    if (active) await request('POST', 'auth.logout', {}, active.token).catch(() => {})
    saveSession(PARENT, null)
    setActive(parent)
    return publicSession(parent)
  },
  logout: () => logoutAll(),
  async api({ method = 'POST', path, args, cacheKey, guest }) {
    if (TOKEN_ENDPOINTS.has(path)) throw invalid('Use the sign-in screen for that.')
    const token = guest ? null : needActive().token
    const key = cacheKey ? `cache:${active?.user || ''}:${active?.student || ''}:${cacheKey}` : null
    try {
      const data = await request(method, path, args || {}, token)
      if (key) await kvSet(key, JSON.stringify({ data, saved: now() }))
      return { data, cached: false }
    } catch (e) {
      if (e.kind === 'offline' && key) {
        const cached = await kvJson(key)
        if (cached) return { data: cached.data, cached: true, saved: cached.saved }
      }
      if (e.kind === 'signed_out') setActive(null)
      throw e
    }
  },
  sync_now: () => syncNow(),
  async learner_status() {
    const scope = learnerScope()
    return {
      learner: await kvJson(`learner:${scope}`),
      entitlement: await kvJson(`entitlement:${scope}`),
      ai_quota: await kvJson(`ai_quota:${scope}`),
      last_sync: await kvGet(`last_sync:${scope}`),
      has_content: (await contentCount(scope, 'area')) > 0,
      pending: await outboxCount(scope),
    }
  },
  local_list: ({ kind, parent }) => contentList(learnerScope(), kind, parent || null),
  local_get: ({ kind, name }) => contentGet(learnerScope(), kind, name),
  async local_quiz({ name }) {
    const scope = learnerScope()
    const quiz = await contentGet(scope, 'quiz', name)
    if (!quiz) throw invalid('This quiz is not on the device yet. Sync first.')
    const rows = []
    for (const q of quiz.questions || []) {
      const row = await contentGet(scope, 'question', q)
      if (row) rows.push(row)
    }
    return { ...quiz, question_rows: rows }
  },
  mine_list: ({ kind }) => mineList(learnerScope(), kind),
  queue_event: ({ kind, payload }) => queue(learnerScope(), kind, payload || {}),
  async outbox_list() {
    const rows = await outboxAll(learnerScope())
    return rows.sort((a, b) => b.created - a.created).map((r) => {
      const payload = { ...r.payload }
      delete payload.attachment_data
      return { uuid: r.uuid, type: r.type, payload, at: r.at, attempts: r.attempts, state: r.state, error: r.error }
    })
  },
  outbox_discard: ({ uuid: id }) => outboxDone(id),
  async wipe_device() {
    await logoutAll()
    dbp = null
    await new Promise((resolve) => {
      const req = indexedDB.deleteDatabase('cbc-tutor')
      req.onsuccess = req.onerror = req.onblocked = () => resolve()
    })
    for (const k of Object.keys(localStorage)) if (k.startsWith('cbc:')) localStorage.removeItem(k)
  },

  // Tauri plugins the screens use
  'plugin:opener|open_url': ({ url }) => {
    // Google sign-in takes this tab and comes back to /learn; a video or PayPal opens beside it
    if (/^https:\/\/accounts\.google\.com\//.test(url)) location.assign(url)
    else window.open(url, '_blank', 'noopener')
  },
  'plugin:deep-link|get_current': () => {
    // Google sign-in comes back to /learn?auth_code=…: hand it to the app as the apps receive it
    const params = new URLSearchParams(location.search)
    const code = params.get('auth_code')
    if (!code) return null
    params.delete('auth_code')
    history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params : '') + location.hash)
    return [`cbctutor://auth?code=${encodeURIComponent(code)}`]
  },
  'plugin:event|listen': () => 0,
  'plugin:event|unlisten': () => null,
}

let nextCallback = 1
window.__TAURI_INTERNALS__ = {
  invoke: async (cmd, args = {}) => {
    const fn = commands[cmd]
    if (!fn) throw invalid(`The web app can't do ${cmd}.`)
    return fn(args)
  },
  transformCallback: () => nextCallback++,
  metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
}
window.__CBC_WEB__ = true
