<script>
  import { onMount } from 'svelte'
  import { refreshState, toast } from '../../lib/app.svelte.js'
  import { api, get, call, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, date, dateTime, level, initials } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'
  import Modal from '../../components/Modal.svelte'
  import ParentGate from '../../components/ParentGate.svelte'
  import { hasPin } from '../../lib/parentPin.js'

  let { params } = $props()
  const id = params.id

  let res = $state(null)
  let error = $state(null)
  let tab = $state('areas')
  let chats = $state(null)
  let pinOpen = $state(false)
  let pin = $state('')
  let pin2 = $state('')
  let msgOpen = $state(false)
  let message = $state('')
  let busy = $state(false)
  let limitsOpen = $state(false)
  let limits = $state({ ai_daily_limit: 0, quiet_from: '', quiet_to: '' })
  let topics = $state(null)

  async function load() {
    error = null
    try {
      res = await get('parent.child_progress', { student: id }, { cache: 'parent:child:' + id })
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  let r = $derived(res?.data)

  async function saveLimits(e) {
    e.preventDefault()
    busy = true
    try {
      const saved = await api('parent.set_child_limits', {
        student: id,
        ai_daily_limit: Number(limits.ai_daily_limit) || 0,
        quiet_from: limits.quiet_from || null,
        quiet_to: limits.quiet_to || null,
      })
      limitsOpen = false
      if (r) r.limits = saved
      toast('Limits saved.', 'ok')
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  function editLimits() {
    limits = { ai_daily_limit: r.limits?.ai_daily_limit || 0, quiet_from: r.limits?.quiet_from || '', quiet_to: r.limits?.quiet_to || '' }
    limitsOpen = true
  }

  async function showChats() {
    tab = 'chats'
    if (!topics) get('parent.child_topics', { student: id }).then((t) => (topics = t)).catch(() => (topics = []))
    if (chats) return
    try {
      chats = await get('parent.child_conversations', { student: id })
    } catch (e) {
      chats = []
      toast(errorText(e), 'error')
    }
  }

  let gate = $state(false)
  function startLearning() {
    if (!hasPin()) gate = true
    else openLearner()
  }

  async function openLearner() {
    busy = true
    try {
      await call('open_learner', { student: id })
      await refreshState()
      go('/', { replace: true })
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      busy = false
    }
  }

  async function savePin(e) {
    e.preventDefault()
    if (pin !== pin2) return toast('The two PINs do not match.', 'error')
    busy = true
    try {
      await api('parent.set_child_pin', { student: id, pin })
      pinOpen = false
      pin = pin2 = ''
      toast('PIN changed. Your child signs in again with the new PIN.', 'ok')
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function toggle() {
    const on = !r.learner.enabled
    if (!on && !confirm(`Switch off ${r.learner.first_name}? They are signed out everywhere, and their place on your plan is freed. Their history is kept.`)) return
    busy = true
    try {
      await api('parent.set_child_enabled', { student: id, enabled: on ? 1 : 0 })
      await load()
      toast(on ? 'Switched on.' : 'Switched off.', 'ok')
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      busy = false
    }
  }

  async function sendMessage(e) {
    e.preventDefault()
    busy = true
    try {
      await api('parent.send_feedback', { student: id, message })
      msgOpen = false
      message = ''
      toast('Message sent to the school.', 'ok')
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  const tone = (s) => ({ Advanced: 'ok', Proficient: 'brand', Emerging: 'warn', Reviewed: 'ok', Returned: 'warn', 'Not submitted': 'bad' })[s] || ''
</script>

<TopBar title={r?.learner.name || 'Progress'} backTo="/">
  {#if r}<a class="btn sm ghost" href={'#/child/' + enc(id) + '/edit'}>Edit</a>{/if}
</TopBar>
<div class="page">
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if r}
    {@const enabled = r.learner.enabled}
    <div class="card">
      <div class="row">
        <div class="avatar lg">{initials(r.learner.name)}</div>
        <div class="grow">
          <h2 style="margin: 0">{r.learner.name}</h2>
          <div class="small muted">{r.learner.grade} {r.learner.school ? '· ' + r.learner.school : ''}</div>
          <div class="small">Learner code <b>{r.learner.learner_code}</b> · last active {ago(r.summary.last_active)}</div>
        </div>
      </div>
      <div class="grid small" style="margin: 14px 0">
        <div><div class="stat">{r.summary.lessons_completed_this_week}</div><div class="small muted">lessons this week</div></div>
        <div><div class="stat">{r.summary.quizzes_this_week}</div><div class="small muted">quizzes this week</div></div>
        <div><div class="stat">{r.ai_questions_this_week}</div><div class="small muted">questions to Mwalimu</div></div>
      </div>
      <div class="row wrap">
        <button class="btn sm" onclick={startLearning} disabled={busy || res.cached || !enabled}>Let them learn here</button>
        <button class="btn sm ghost" onclick={() => (pinOpen = true)} disabled={res.cached}>Change PIN</button>
        <button class="btn sm ghost" onclick={editLimits} disabled={res.cached || !r.limits}>Limits</button>
        <button class="btn sm ghost" onclick={() => (msgOpen = true)} disabled={res.cached || !r.learner.school}>Message the school</button>
        <button class="btn sm ghost" class:danger={enabled} onclick={toggle} disabled={busy || res.cached}>{enabled ? 'Switch off' : 'Switch on'}</button>
      </div>
    </div>

    {#if r.highlights}
      <!-- The report card: the week in a sentence, then each learning area at a glance. -->
      <section class="report">
        <p class="report-line">{r.highlights.headline}</p>
        <div class="row wrap" style="gap: 8px; margin-bottom: 12px">
          {#if r.highlights.strong}
            <span class="pill ok">⭐ Best: {r.highlights.strong.title}{r.highlights.strong.quiz_average != null ? ` · ${Math.round(r.highlights.strong.quiz_average)}%` : ''}</span>
          {/if}
          {#each r.highlights.practise as p}<span class="pill warn">🎯 Practise: {p.title} · {p.why}</span>{/each}
        </div>
        <div class="area-bars">
          {#each r.learning_areas as a}
            <div class="area-bar">
              <span class="area-name">{a.title}</span>
              <span class="bar"><i style="width: {a.percent}%"></i></span>
              <span class="area-num">{a.percent}%{a.quiz_average != null ? ` · ${Math.round(a.quiz_average)}%` : ''}</span>
            </div>
          {/each}
        </div>
        <p class="small muted" style="margin: 8px 0 0">Bars show lessons done; the second number is the quiz average. You get this summary by email every Sunday.</p>
      </section>
    {/if}

    <div class="tabs">
      <button class="tab" class:on={tab === 'areas'} onclick={() => (tab = 'areas')}>Learning areas</button>
      <button class="tab" class:on={tab === 'school'} onclick={() => (tab = 'school')}>School work</button>
      <button class="tab" class:on={tab === 'quizzes'} onclick={() => (tab = 'quizzes')}>Quizzes</button>
      <button class="tab" class:on={tab === 'chats'} onclick={showChats}>Mwalimu chats</button>
    </div>

    {#if tab === 'areas'}
      {#each r.learning_areas as a}
        <div class="card">
          <div class="row between"><b>{a.title}</b><span class="small muted">{a.completed}/{a.lessons} lessons</span></div>
          <div class="bar" style="margin: 8px 0"><i style="width: {a.percent}%"></i></div>
          <div class="small muted">
            {a.quiz_average != null ? `Quiz average ${Math.round(a.quiz_average)}% · ${level(a.quiz_average)}` : 'No quizzes yet'}
            {#if a.minutes} · {a.minutes} min{/if}
          </div>
        </div>
      {:else}
        <p class="muted">No lessons for this grade yet.</p>
      {/each}
    {:else if tab === 'school'}
      {#if r.competencies.length}
        <h3>Teacher observations</h3>
        {#each r.competencies as c}
          <div class="card flat">
            <div class="row between"><span class="pill {tone(c.status)}">{c.status}</span><span class="small muted">{date(c.date)}</span></div>
            <p style="margin: 8px 0 4px">{c.outcome || c.learning_outcome}</p>
            {#if c.comments}<div class="small muted">“{c.comments}”</div>{/if}
          </div>
        {/each}
      {/if}
      {#if r.assessments.length}
        <h3>Assessments</h3>
        {#each r.assessments as s}
          <div class="card flat row">
            <div class="grow"><b>{s.subject || s.assessment_type}</b><div class="small muted">{s.assessment_type} · {date(s.date)}</div>{#if s.comments}<div class="small">{s.comments}</div>{/if}</div>
            <b>{s.score}{s.max_score ? '/' + s.max_score : ''}</b>
          </div>
        {/each}
      {/if}
      <h3>Assignments</h3>
      {#each r.assignments as w}
        <div class="card flat row">
          <div class="grow"><b>{w.title}</b><div class="small muted">{w.type}{w.due_date ? ' · due ' + date(w.due_date) : ''}</div>{#if w.remarks}<div class="small">“{w.remarks}”</div>{/if}</div>
          <span class="pill {tone(w.status)}">{w.grade_given || w.status}</span>
        </div>
      {:else}
        <p class="muted">No assignments yet.</p>
      {/each}
    {:else if tab === 'quizzes'}
      {#each r.recent_quizzes as q}
        <div class="card flat row">
          <div class="grow"><b>{q.lesson_title || q.quiz}</b><div class="small muted">Attempt {q.attempt_number || 1} · {dateTime(q.time_completed || q.creation)}</div></div>
          <span class="pill {q.score >= 50 ? 'ok' : 'warn'}">{Math.round(q.score)}%</span>
        </div>
      {:else}
        <p class="muted">No quizzes taken yet.</p>
      {/each}
    {:else}
      {#if topics?.length}
        <div class="card flat" style="margin-bottom: 12px">
          <div class="small muted" style="margin-bottom: 6px">Topics asked about in the last 30 days</div>
          <div class="row wrap" style="gap: 6px">
            {#each topics as t}<span class="pill">{t.topic} · {t.questions}</span>{/each}
          </div>
        </div>
      {/if}
      {#if !chats}
        <Loading />
      {:else}
        {#each chats as c}
          <div class="card flat">
            <div class="small muted">{dateTime(c.date)}{c.topic ? ' · ' + c.topic : ''}</div>
            <div>{c.question}</div>
          </div>
        {:else}
          <p class="muted">No questions to Mwalimu yet.</p>
        {/each}
      {/if}
    {/if}
  {/if}
</div>

<Modal bind:open={limitsOpen} title="Limits for {r?.learner.first_name || 'this child'}">
  <form onsubmit={saveLimits}>
    <label class="field"><span>Mwalimu questions a day</span>
      <input type="number" min="0" max="500" inputmode="numeric" bind:value={limits.ai_daily_limit} />
    </label>
    <p class="small muted" style="margin-top: -8px">0 uses the plan's limit. You can set fewer, never more than the plan allows.</p>
    <div class="row">
      <label class="field grow"><span>Quiet from</span><input type="time" bind:value={limits.quiet_from} /></label>
      <label class="field grow"><span>until</span><input type="time" bind:value={limits.quiet_to} /></label>
    </div>
    <p class="small muted" style="margin-top: -8px">Mwalimu doesn't answer during quiet hours (bedtime, say). Lessons and quizzes still work. Leave both empty for none.</p>
    <button class="btn block" disabled={busy}>{busy ? 'Saving…' : 'Save limits'}</button>
  </form>
</Modal>

<Modal bind:open={pinOpen} title="New PIN">
  <form onsubmit={savePin}>
    <label class="field"><span>New PIN (4–8 digits)</span><input class="pin-input" type="password" inputmode="numeric" minlength="4" maxlength="8" bind:value={pin} required /></label>
    <label class="field"><span>PIN again</span><input class="pin-input" type="password" inputmode="numeric" maxlength="8" bind:value={pin2} required /></label>
    <button class="btn block" disabled={busy}>Save PIN</button>
  </form>
</Modal>

<Modal bind:open={msgOpen} title="Message the school">
  <form onsubmit={sendMessage}>
    <p class="small muted">Teachers at {r?.learner.school} can read and reply. Replies appear under Messages.</p>
    <label class="field"><span>Message</span><textarea bind:value={message} maxlength="4000" required></textarea></label>
    <button class="btn block" disabled={busy || message.trim().length < 3}>Send</button>
  </form>
</Modal>


<ParentGate bind:open={gate} mode="set" onpass={openLearner} />

<style>
  .report { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 16px; margin: 14px 0; box-shadow: var(--shadow); border-top: 5px solid var(--brand); }
  .report-line { font-size: 1.15rem; font-weight: 700; margin: 0 0 10px; line-height: 1.4; }
  .area-bars { display: grid; gap: 8px; }
  .area-bar { display: grid; grid-template-columns: minmax(110px, 200px) 1fr auto; gap: 10px; align-items: center; font-size: 0.88rem; }
  .area-bar .bar { height: 10px; }
  .area-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .area-num { color: var(--muted); font-variant-numeric: tabular-nums; min-width: 72px; text-align: right; }
  @media (max-width: 520px) { .area-bar { grid-template-columns: 1fr auto; } .area-bar .bar { grid-column: 1 / -1; order: 3; } }
</style>
