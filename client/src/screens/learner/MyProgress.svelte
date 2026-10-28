<script>
  import { onMount } from 'svelte'
  import { date, level, minutes, plain } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'

  let areas = $state([])
  let competencies = $state([])
  let totals = $state({ lessons: 0, done: 0, time: 0, quizzes: 0 })
  let loading = $state(true)

  onMount(async () => {
    const done = await L.progressByLesson()
    const best = await L.bestScores()
    const attempts = await L.mine('quiz_attempt')
    const out = []
    let t = { lessons: 0, done: 0, time: 0, quizzes: attempts.length }
    for (const a of await L.list('area')) {
      const lessons = await L.list('lesson', a.name)
      const finished = lessons.filter((l) => done[l.name]?.status === 'Completed').length
      const scores = lessons.filter((l) => l.quiz && best[l.quiz] != null).map((l) => best[l.quiz])
      const time = lessons.reduce((s, l) => s + Number(done[l.name]?.time_spent || 0), 0)
      t.lessons += lessons.length
      t.done += finished
      t.time += time
      out.push({ ...a, total: lessons.length, finished, avg: scores.length ? scores.reduce((x, y) => x + y, 0) / scores.length : null, time })
    }
    areas = out
    totals = t
    competencies = []
    for (const c of await L.mine('competency')) {
      const o = c.learning_outcome ? await L.one('outcome', c.learning_outcome) : null
      competencies.push({ ...c, outcome: o ? plain(o.description) : c.learning_outcome })
    }
    loading = false
  })

  const tone = (s) => ({ Advanced: 'ok', Proficient: 'brand', Emerging: 'warn' })[s] || ''
</script>

<TopBar title="My progress" />
<div class="page">
  {#if loading}
    <Loading />
  {:else}
    <div class="grid small">
      <div class="card"><div class="stat">{totals.done}</div><div class="small muted">lessons done of {totals.lessons}</div></div>
      <div class="card"><div class="stat">{totals.quizzes}</div><div class="small muted">quizzes taken</div></div>
      <div class="card"><div class="stat">{minutes(totals.time)}</div><div class="small muted">spent learning</div></div>
    </div>

    <div class="section"><h2>By learning area</h2></div>
    {#each areas.filter((a) => a.total) as a}
      <div class="card">
        <div class="row between"><b>{a.title}</b><span class="small muted">{a.finished}/{a.total}</span></div>
        <div class="bar" style="margin: 8px 0"><i style="width: {(100 * a.finished) / a.total}%"></i></div>
        <div class="small muted">
          {#if a.avg != null}Quiz average {Math.round(a.avg)}% · {level(a.avg)}{:else}No quizzes yet{/if}
        </div>
      </div>
    {:else}
      <p class="muted">Finish a lesson to see your progress here.</p>
    {/each}

    {#if competencies.length}
      <div class="section"><h2>From your teachers</h2></div>
      {#each competencies as c}
        <div class="card flat">
          <div class="row between"><span class="pill {tone(c.status)}">{c.status}</span><span class="small muted">{date(c.date)}</span></div>
          <p style="margin: 8px 0 4px">{c.outcome}</p>
          {#if c.comments}<div class="small muted">“{c.comments}”</div>{/if}
        </div>
      {/each}
    {/if}
  {/if}
</div>
