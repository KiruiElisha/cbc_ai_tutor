<script>
  import { onMount } from 'svelte'
  import { app } from '../../lib/app.svelte.js'
  import { get } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let res = $state(null)
  let error = $state(null)

  async function load() {
    error = null
    try {
      res = await get('teacher.dashboard', {}, { cache: 'teacher:dashboard' })
    } catch (e) {
      error = e
    }
  }
  onMount(load)
  let d = $derived(res?.data)
</script>

<TopBar title={d?.instructor_name ? `Habari, ${d.instructor_name.split(' ')[0]}` : 'Home'}>
  <a class="btn sm" href="#/assignment/new">+ Assignment</a>
</TopBar>
<div class="page">
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if d}
    {#if !d.school}
      <div class="banner warn">Your account is not linked to a school yet, so no learners show. Ask the school admin to set your school on your Instructor record.</div>
    {:else}
      <p class="muted" style="margin-top: 0">{d.school}</p>
    {/if}
    <div class="grid small">
      <a class="card tap" href="#/students"><div class="stat">{d.learners}</div><div class="small muted">learners</div></a>
      <a class="card tap" href="#/assignments"><div class="stat">{d.open_assignments}</div><div class="small muted">open assignments</div></a>
      <a class="card tap" href="#/assignments?review=1"><div class="stat" style="color: {d.to_review ? 'var(--warn)' : ''}">{d.to_review}</div><div class="small muted">to review</div></a>
      <a class="card tap" href="#/inbox"><div class="stat" style="color: {d.unanswered_feedback ? 'var(--warn)' : ''}">{d.unanswered_feedback}</div><div class="small muted">parent messages to answer</div></a>
    </div>
    {#if d.grades.length}
      <div class="section"><h2>Classes</h2></div>
      <div class="row wrap">
        {#each d.grades as g}
          <a class="card tap flat" style="min-width: 140px" href={'#/students?grade=' + enc(g.grade)}><b>{g.grade}</b><div class="small muted">{g.learners} learners</div></a>
        {/each}
      </div>
    {/if}
  {/if}
</div>
