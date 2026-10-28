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
      {#each d.children as c}
        <div class="card">
          <div class="row">
            <div class="avatar lg">{initials(c.name)}</div>
            <div class="grow">
              <h3 style="margin: 0">{c.name}</h3>
              <div class="small muted">{c.grade || 'No grade'} · code <b>{c.learner_code}</b></div>
              {#if !c.enabled}<span class="pill bad">Switched off</span>{/if}
            </div>
          </div>
          <div class="grid small" style="margin: 14px 0">
            <div><div class="stat">{c.lessons_completed_this_week}</div><div class="small muted">lessons this week</div></div>
            <div><div class="stat">{c.quiz_average_this_week != null ? Math.round(c.quiz_average_this_week) + '%' : '–'}</div><div class="small muted">quiz average</div></div>
            <div><div class="small muted">Last active</div><b>{ago(c.last_active)}</b></div>
          </div>
          <div class="row wrap">
            <a class="btn sm" href={'#/child/' + enc(c.student)}>Progress</a>
            {#if c.enabled}
              <button class="btn sm soft" onclick={() => openLearner(c)} disabled={opening === c.student || res.cached}>
                {opening === c.student ? 'Opening…' : `Let ${c.first_name || c.name.split(' ')[0]} learn here`}
              </button>
            {/if}
          </div>
        </div>
      {/each}
      <p class="small muted center">Plan: {d.subscription.plan || d.subscription.status} · {d.children.filter((c) => c.enabled).length} of {d.subscription.max_learners} learner places used</p>
    {/if}
  {/if}
</div>
