<script>
  import { onMount } from 'svelte'
  import { app, syncNow, refreshState, toast } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, date } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ParentGate from '../../components/ParentGate.svelte'
  import { hasPin } from '../../lib/parentPin.js'
  import { subject } from '../../lib/subjects.js'
  import * as Review from '../../lib/review.js'
  import { fresh } from '../../lib/badges.js'
  import { examName } from '../../lib/exam.js'

  let st = $state(null)
  let areas = $state([])
  let counts = $state({})
  let resume = $state(null)
  let due = $state(0)
  let loading = $state(true)
  let firstSync = $state(false)
  let act = $state({ streak: 0, today: 0, goal: 3 })
  let practice = $state({ questions: [], total: 0 })

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
    practice = await Review.due(app.session?.profile?.learner?.student)
    for (const b of await fresh(app.session?.profile?.learner?.student)) toast(`${b.icon} New badge: ${b.name}!`, 'ok')
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

  let gate = $state(false)

  function backToParent() {
    if (hasPin()) gate = true
    else leave()
  }

  async function leave() {
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
    <!-- Today: everything worth doing now, in one place. -->
    <section class="today">
      <div class="today-head"><h2>Today</h2><span class="small muted">{new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'short' })}</span></div>
      {#if resume}
        <a class="today-row" href={'#/lesson/' + enc(resume.l.name)}>
          <span class="today-ico play">▶</span>
          <span class="grow"><small>Continue where you stopped</small><b>{resume.l.title}</b>
            <span class="bar" style="margin-top: 6px; display: block"><i style="width: {resume.p.progress || 0}%"></i></span></span>
        </a>
      {/if}
      <a class="today-row" href="#/review">
        <span class="today-ico">🎯</span>
        <span class="grow">
          <small>Today's practice</small>
          <b>{practice.questions.length ? `${practice.questions.length} questions · about ${Math.max(1, Math.round(practice.questions.length * 0.5))} min` : 'All caught up'}</b>
        </span>
        {#if practice.questions.length}<span class="pill brand">Go</span>{/if}
      </a>
      {#if due}
        <a class="today-row" href="#/work">
          <span class="today-ico">📝</span>
          <span class="grow"><small>Assignments</small><b>{due} to hand in</b></span>
        </a>
      {/if}
    </section>

    <div class="quick">
      <a class="quick-item" href="#/tutor" style="--c: #0b7a3d"><span class="chip">💬</span><b>Ask Mwalimu</b><small>Your tutor</small></a>
      <a class="quick-item" href="#/drill" style="--c: #2563eb"><span class="chip">🧮</span><b>Maths drills</b><small>Works offline</small></a>
      <a class="quick-item" href="#/work" style="--c: #ea580c"><span class="chip">📝</span><b>Assignments</b><small>{due ? `${due} to do` : 'All done'}</small></a>
      <a class="quick-item" href="#/exam" style="--c: #b8211a"><span class="chip">📝</span><b>{examName(st?.learner?.grade || app.session?.profile?.learner?.grade)}</b><small>A timed mixed paper</small></a>
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
          {#if c.total}
            {@const pct = Math.round((100 * c.done) / c.total)}
            <span class="sring" style="--p: {pct}" aria-label="{pct}% done"><b>{pct}%</b></span>
          {/if}
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

<ParentGate bind:open={gate} mode="check" onpass={leave} />
