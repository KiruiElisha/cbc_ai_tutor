<script>
  import { onMount } from 'svelte'
  import { refreshState } from '../../lib/app.svelte.js'
  import { get, call, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, date, initials } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let res = $state(null)
  let error = $state(null)
  let opening = $state(null)

  async function load() {
    error = null
    try {
      res = await get('parent.dashboard', {}, { cache: 'parent:dashboard' })
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  let d = $derived(res?.data)

  async function openLearner(child) {
    opening = child.student
    try {
      await call('open_learner', { student: child.student })
      await refreshState()
      go('/', { replace: true })
    } catch (e) {
      error = e
    } finally {
      opening = null
    }
  }
</script>

<TopBar title="My children">
  <a class="btn sm" href="#/child/new">+ Add child</a>
</TopBar>
<div class="page">
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if d}
    {#if !d.subscription.active}
      <a class="banner bad" href="#/plans" style="text-decoration: none">🔒 <span class="grow">Your plan has ended. Paid lessons and Mwalimu are locked. <b>Renew now</b></span></a>
    {:else if d.subscription.status === 'Trial'}
      <a class="banner info" href="#/plans" style="text-decoration: none">🎁 <span class="grow">Free trial until {date(d.subscription.until)}. <b>See plans</b></span></a>
    {/if}

    {#if !d.children.length}
      <Empty icon="🧒🏾" title="Add your first child">
        <p>Each child gets a learner code and PIN to sign in on any phone, tablet or computer.</p>
        <a class="btn" href="#/child/new">Add a child</a>
      </Empty>
    {:else}
      <div class="section"><h2>Who's learning today?</h2></div>
      <p class="small muted" style="margin: -4px 0 12px">Tap <b>Start learning</b> to hand this device to your child. Their lessons, quizzes and Mwalimu open straight away.</p>
      <div class="who">
        {#each d.children as c}
          {@const first = c.first_name || c.name.split(' ')[0]}
          <div class="kid">
            <div class="kid-top">
              <div class="avatar">{initials(c.name)}</div>
              <div class="grow">
                <h3 style="margin: 0">{c.name}</h3>
                <div class="small muted">{c.grade || 'No grade'} · code <b>{c.learner_code}</b></div>
                {#if !c.enabled}<span class="pill bad">Switched off</span>{/if}
              </div>
            </div>
            {#if c.enabled}
              <button class="kid-learn" onclick={() => openLearner(c)} disabled={opening === c.student || res.cached}>
                <span class="play">▶</span>{opening === c.student ? 'Opening…' : `Start learning as ${first}`}
              </button>
            {/if}
            <div class="kid-stats">
              <div><b>{c.lessons_completed_this_week}</b><small>lessons this week</small></div>
              <div><b>{c.quiz_average_this_week != null ? Math.round(c.quiz_average_this_week) + '%' : '–'}</b><small>quiz average</small></div>
              <div><b style="font-size: 0.92rem; padding: 3px 0">{ago(c.last_active)}</b><small>last active</small></div>
            </div>
            <a class="btn sm ghost" href={'#/child/' + enc(c.student)}>See {first}'s progress</a>
          </div>
        {/each}
        {#if d.children.filter((c) => c.enabled).length < d.subscription.max_learners}
          <a class="kid-add" href="#/child/new"><span>＋</span>Add a child</a>
        {/if}
      </div>
      <p class="small muted center">Plan: {d.subscription.plan || d.subscription.status} · {d.children.filter((c) => c.enabled).length} of {d.subscription.max_learners} learner places used</p>
    {/if}
  {/if}
</div>
