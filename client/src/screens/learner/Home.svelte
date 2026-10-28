<script>
  import { onMount } from 'svelte'
  import { app, syncNow, refreshState } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, date } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'

  let st = $state(null)
  let areas = $state([])
  let counts = $state({})
  let resume = $state(null)
  let due = $state(0)
  let loading = $state(true)
  let firstSync = $state(false)

  const first = () => (app.session?.profile?.learner?.first_name || app.session?.profile?.learner?.name || '').split(' ')[0]

  async function load() {
    st = await L.status()
    areas = await L.list('area')
    const done = await L.progressByLesson()
    const c = {}
    let latest = null
    for (const a of areas) {
      const lessons = await L.list('lesson', a.name)
      const finished = lessons.filter((l) => done[l.name]?.status === 'Completed').length
      c[a.name] = { total: lessons.length, done: finished }
      for (const l of lessons) {
        const p = done[l.name]
        if (p && p.status !== 'Completed' && (!latest || String(p.last_opened) > String(latest.p.last_opened))) latest = { l, p }
      }
    }
    counts = c
    resume = latest
    const subs = Object.fromEntries((await L.mine('submission')).map((s) => [s.assignment, s]))
    due = (await L.mine('assignment')).filter((a) => a.status === 'Published' && !subs[a.name]).length
    loading = false
  }

  onMount(() => {
    load().then(async () => {
      if (!st.has_content) {
        firstSync = true
        await syncNow()
        firstSync = false
        await load()
      }
    })
    const onSynced = () => load()
    window.addEventListener('cbc:synced', onSynced)
    return () => window.removeEventListener('cbc:synced', onSynced)
  })

  async function backToParent() {
    try {
      await call('back_to_parent')
      await refreshState()
      go('/', { replace: true })
    } catch (e) {
      alert(errorText(e))
    }
  }

  const icons = { Mathematics: '➗', English: '📖', Kiswahili: '🗣️', Science: '🔬', Social: '🌍', Creative: '🎨', Religious: '🕊️', Agriculture: '🌱', Environmental: '🌳', Language: '🔤', Pre: '🛠️', Computer: '💻', Physics: '🧲', Chemistry: '⚗️', Biology: '🧬', Geography: '🗺️', History: '🏛️', Business: '💼', Physical: '⚽', Community: '🤝' }
  const iconFor = (title) => Object.entries(icons).find(([k]) => title.includes(k))?.[1] || '📘'
</script>

<div class="page">
  <div class="hero">
    <div class="row between wrap">
      <div>
        <h1 style="margin: 0">Habari, {first() || 'learner'}! 👋</h1>
        <div class="muted">{st?.learner?.grade || app.session?.profile?.learner?.grade || ''}</div>
      </div>
      {#if app.parentWaiting}
        <button class="btn sm sun" onclick={backToParent}>Back to parent</button>
      {/if}
    </div>
    {#if st?.entitlement && !st.entitlement.active}
      <div class="banner" style="margin: 14px 0 0">🔒 Your family plan has ended. Free lessons still work. Ask a parent to renew.</div>
    {:else if st?.entitlement?.status === 'Trial'}
      <div class="small muted" style="margin-top: 8px">Free trial until {date(st.entitlement.until)}</div>
    {/if}
  </div>

  {#if loading || firstSync}
    <Loading />
    {#if firstSync}<p class="center muted">Getting your lessons ready…</p>{/if}
  {:else if !areas.length}
    <Empty icon="📶" title="No lessons on this device yet">
      <p>Connect to the internet and tap Sync.</p>
      <button class="btn" onclick={() => syncNow().then(load)} disabled={app.syncing}>{app.syncing ? 'Syncing…' : 'Sync now'}</button>
    </Empty>
  {:else}
    {#if resume}
      <a class="card tap row" href={'#/lesson/' + enc(resume.l.name)}>
        <span style="font-size: 1.8rem">▶️</span>
        <div class="grow"><div class="small muted">Continue</div><b>{resume.l.title}</b></div>
        <div class="bar" style="width: 80px"><i style="width: {resume.p.progress || 0}%"></i></div>
      </a>
    {/if}

    <div class="grid small" style="margin-top: 12px">
      <a class="card tap" href="#/tutor"><div style="font-size: 1.6rem">💬</div><b>Ask Mwalimu</b><div class="small muted">Your AI tutor</div></a>
      <a class="card tap" href="#/work"><div style="font-size: 1.6rem">📝</div><b>Assignments</b><div class="small muted">{due ? `${due} to do` : 'All done'}</div></a>
    </div>

    <div class="section"><h2>Learning areas</h2></div>
    <div class="grid">
      {#each areas as a}
        {@const c = counts[a.name] || { total: 0, done: 0 }}
        <a class="card tap" href={'#/area/' + enc(a.name)}>
          <div class="row">
            <span style="font-size: 1.8rem">{iconFor(a.title)}</span>
            <div class="grow"><b>{a.title}</b><div class="small muted">{c.total ? `${c.done} of ${c.total} lessons` : 'Lessons coming soon'}</div></div>
          </div>
          {#if c.total}<div class="bar" style="margin-top: 10px"><i style="width: {(100 * c.done) / c.total}%"></i></div>{/if}
        </a>
      {/each}
    </div>

    <p class="small muted center" style="margin-top: 20px">
      {#if app.syncing}Syncing…{:else}Last synced {ago(app.lastSync || st?.last_sync)}{/if}
      {#if app.pending} · {app.pending} waiting to send{/if}
      · <a href="#/sync">Sync</a>
    </p>
  {/if}
</div>
