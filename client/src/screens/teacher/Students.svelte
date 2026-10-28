<script>
  import { onMount } from 'svelte'
  import { get } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, initials } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let { params } = $props()
  let grade = $state(params.grade || '')
  let txt = $state('')
  let grades = $state([])
  let res = $state(null)
  let error = $state(null)
  let timer

  async function load() {
    error = null
    try {
      res = await get('teacher.students', { grade: grade || null, txt: txt || null }, { cache: `teacher:students:${grade}:${txt}` })
    } catch (e) {
      error = e
    }
  }

  onMount(async () => {
    load()
    grades = await get('curriculum.grades', {}, { guest: true }).catch(() => [])
  })

  function search() {
    clearTimeout(timer)
    timer = setTimeout(load, 300)
  }
</script>

<TopBar title="Learners" />
<div class="page">
  <div class="row wrap" style="margin-bottom: 12px">
    <input class="grow" placeholder="Search by name or learner code" bind:value={txt} oninput={search} />
    <select bind:value={grade} onchange={() => go('/students' + (grade ? '?grade=' + enc(grade) : ''), { replace: true })}>
      <option value="">All grades</option>
      {#each grades as g}<option value={g.name}>{g.program_name}</option>{/each}
    </select>
  </div>
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if res}
    {#each res.data as s}
      <a class="card tap row flat" href={'#/student/' + enc(s.student)}>
        <div class="avatar">{initials(s.name)}</div>
        <div class="grow">
          <b>{s.name}</b>
          <div class="small muted">{s.grade} · {s.learner_code} · active {ago(s.last_active)}</div>
        </div>
        <div class="right small">
          <div>{s.lessons_completed_this_week} lessons</div>
          <div class="muted">{s.quiz_average_this_week != null ? Math.round(s.quiz_average_this_week) + '% quizzes' : ''}</div>
        </div>
      </a>
    {:else}
      <Empty icon="👧🏾" title="No learners found">
        <p>Learners appear here when their parent picks your school for them.</p>
      </Empty>
    {/each}
  {/if}
</div>
