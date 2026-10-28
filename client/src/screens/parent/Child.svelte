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

  async function showChats() {
    tab = 'chats'
    if (chats) return
    try {
      chats = await get('parent.child_conversations', { student: id })
    } catch (e) {
      chats = []
      toast(errorText(e), 'error')
    }
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
        <button class="btn sm" onclick={openLearner} disabled={busy || res.cached || !enabled}>Let them learn here</button>
        <button class="btn sm ghost" onclick={() => (pinOpen = true)} disabled={res.cached}>Change PIN</button>
        <button class="btn sm ghost" onclick={() => (msgOpen = true)} disabled={res.cached || !r.learner.school}>Message the school</button>
        <button class="btn sm ghost" class:danger={enabled} onclick={toggle} disabled={busy || res.cached}>{enabled ? 'Switch off' : 'Switch on'}</button>
      </div>
    </div>

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
