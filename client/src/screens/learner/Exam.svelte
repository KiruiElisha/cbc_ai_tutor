<script>
  import { onMount, onDestroy } from 'svelte'
  import { app } from '../../lib/app.svelte.js'
  import { safeHtml, level } from '../../lib/format.js'
  import { paper, mark, examName, PER_QUESTION_SECONDS } from '../../lib/exam.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'

  const grade = app.session?.profile?.learner?.grade || ''
  const title = examName(grade)
  let questions = $state(null)
  let chosen = $state({})
  let step = $state(0)
  let left = $state(0)
  let started = $state(false)
  let result = $state(null)
  let size = $state(20)
  let timer

  onMount(async () => {
    questions = await paper(40)
  })
  onDestroy(() => clearInterval(timer))

  function start() {
    questions = questions.slice(0, size)
    left = questions.length * PER_QUESTION_SECONDS
    started = true
    timer = setInterval(() => {
      left--
      if (left <= 0) finish()
    }, 1000)
  }

  function finish() {
    clearInterval(timer)
    result = mark(questions, chosen)
    window.scrollTo(0, 0)
  }

  const clock = (s) => `${Math.floor(Math.max(s, 0) / 60)}:${String(Math.max(s, 0) % 60).padStart(2, '0')}`
  let q = $derived(questions?.[step])
  let answered = $derived(Object.keys(chosen).length)
</script>

<TopBar title={title} backTo="/" />
<div class="page" style="max-width: 760px">
  {#if !questions}
    <Loading />
  {:else if questions.length < 5}
    <Empty icon="📝" title="Not enough questions yet">
      <p>Exam practice mixes questions from your lesson quizzes. Sync to get more lessons, then come back.</p>
    </Empty>
  {:else if !started}
    <div class="card stack">
      <h2 style="margin: 0">{title}</h2>
      <p class="muted" style="margin: 0">A mixed paper from all your learning areas, timed like the real exam. At the end you see how you did in each area. Practice papers are not sent to your teacher.</p>
      <div class="row wrap">
        {#each [10, 20, 40].filter((n) => n <= questions.length || n === 10) as n}
          <button class="tab" class:on={size === Math.min(n, questions.length)} onclick={() => (size = Math.min(n, questions.length))}>{Math.min(n, questions.length)} questions · {Math.round((Math.min(n, questions.length) * PER_QUESTION_SECONDS) / 60)} min</button>
        {/each}
      </div>
      <button class="btn" onclick={start}>Start the paper</button>
    </div>
  {:else if result}
    <div class="hero center">
      <div class="stat">{result.score}%</div>
      <div>{result.right} of {result.total} right · {level(result.score)}</div>
    </div>
    <div class="section"><h2>By learning area</h2></div>
    {#each result.areas as a}
      <div class="card flat row" style="margin-bottom: 8px">
        <b class="grow">{a.area}</b>
        <span class="pill {a.right / a.total >= 0.6 ? 'ok' : 'warn'}">{a.right}/{a.total}</span>
      </div>
    {/each}
    {#if result.areas[0] && result.areas[0].right / result.areas[0].total < 0.6}
      <p class="muted">Practise <b>{result.areas[0].area}</b> next: it had the most misses.</p>
    {/if}
    <a class="btn block" href="#/" style="margin-top: 12px">Done</a>
  {:else}
    <div class="row between small" style="margin-bottom: 8px">
      <span class="muted">Question {step + 1} of {questions.length} · {q.area}</span>
      <span class="pill {left < 120 ? 'bad' : 'brand'}">⏱ {clock(left)}</span>
    </div>
    <div class="bar" style="margin-bottom: 12px"><i style="width: {(100 * answered) / questions.length}%"></i></div>
    <div class="card">
      <div class="prose" style="font-weight: 600; margin-bottom: 12px">{@html safeHtml(q.question)}</div>
      {#each q.options as o, j}
        <button class="option" class:on={chosen[q.name] === o.id} onclick={() => (chosen[q.name] = o.id)}>
          <span class="mark">{String.fromCharCode(65 + j)}</span><span class="grow">{o.text}</span>
        </button>
      {/each}
    </div>
    <div class="row" style="margin-top: 14px">
      {#if step > 0}<button class="btn ghost" onclick={() => step--}>← Back</button>{/if}
      {#if step < questions.length - 1}
        <button class="btn grow" onclick={() => step++}>{chosen[q.name] ? 'Next' : 'Skip for now'}</button>
      {:else}
        <button class="btn grow" onclick={finish}>Hand in ({answered} of {questions.length} answered)</button>
      {/if}
    </div>
  {/if}
</div>
