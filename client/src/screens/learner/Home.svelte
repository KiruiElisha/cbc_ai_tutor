<script>
  import { onMount } from 'svelte'
  import { app, syncNow, refreshState } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, date } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import { subject } from '../../lib/subjects.js'

  let st = $state(null)
  let areas = $state([])
  let counts = $state({})
  let resume = $state(null)
  let due = $state(0)
  let loading = $state(true)
  let firstSync = $state(false)
  let act = $state({ streak: 0, today: 0, goal: 3 })

  const first = () => (app.session?.profile?.learner?.first_name || app.session?.profile?.learner?.name || '').split(' ')[0]

  async function load() {
    st = await L.status()
    act = await L.activity()
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

</script>

<div class="page">
  <section class="hero home-hero">
    <div class="row between wrap" style="align-items: flex-start">
      <div>
        <div class="hello">Habari, {first() || 'learner'}! 👋</div>
        <div class="muted">{st?.learner?.grade || app.session?.profile?.learner?.grade || ''} · Let's learn something new today</div>
      </div>
      {#if app.parentWaiting}
        <button class="btn sm sun" onclick={backToParent}>Back to parent</button>
      {/if}
    </div>
    <div class="hero-stats">
      <div class="chip-stat"><span class="big">🔥 {act.streak}</span><span>day{act.streak === 1 ? '' : 's'} in a row</span></div>
      <div class="chip-stat">
        <span class="ring" style="--p: {(100 * act.today) / act.goal}"><b>{act.today}/{act.goal}</b></span>
        <span>today's goal</span>
      </div>
    </div>
    {#if st?.entitlement && !st.entitlement.active}
      <div class="banner" style="margin: 14px 0 0">🔒 Your family plan has ended. Free lessons still work. Ask a parent to renew.</div>
    {:else if st?.entitlement?.status === 'Trial'}
      <div class="small muted" style="margin-top: 10px">Free trial until {date(st.entitlement.until)}</div>
    {/if}
  </section>

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
      <a class="card tap continue" href={'#/lesson/' + enc(resume.l.name)}>
        <span class="play">▶</span>
        <div class="grow">
          <div class="small muted">Continue where you stopped</div>
          <b>{resume.l.title}</b>
          <div class="bar" style="margin-top: 8px"><i style="width: {resume.p.progress || 0}%"></i></div>
        </div>
      </a>
    {/if}

    <div class="quick">
      <a class="quick-item" href="#/tutor" style="--c: #0f766e"><span class="chip">💬</span><b>Ask Mwalimu</b><small>Your tutor</small></a>
      <a class="quick-item" href="#/drill" style="--c: #2563eb"><span class="chip">🧮</span><b>Maths drills</b><small>Works offline</small></a>
      <a class="quick-item" href="#/work" style="--c: #ea580c"><span class="chip">📝</span><b>Assignments</b><small>{due ? `${due} to do` : 'All done'}</small></a>
      <a class="quick-item" href="#/progress" style="--c: #ca8a04"><span class="chip">⭐</span><b>My progress</b><small>Scores and badges</small></a>
    </div>

    <div class="section"><h2>Learning areas</h2></div>
    <div class="subjects">
      {#each areas as a}
        {@const c = counts[a.name] || { total: 0, done: 0 }}
        {@const t = subject(a.title)}
        <a class="subject tap" href={'#/area/' + enc(a.name)} style={t.style}>
          <span class="chip">{t.icon}</span>
          <b>{a.title}</b>
          <small>{c.total ? `${c.done} of ${c.total} lessons` : 'Coming soon'}</small>
          <div class="bar"><i style="width: {c.total ? (100 * c.done) / c.total : 0}%"></i></div>
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
