<script>
  import { onMount } from 'svelte'
  import { queue } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import { level, nowString, safeHtml } from '../../lib/format.js'
  import { markQuiz, shuffle } from '../../lib/quiz.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import AskMwalimu from '../../components/AskMwalimu.svelte'
  import { plain } from '../../lib/format.js'

  let { params } = $props()
  let quiz = $state(null)
  let questions = $state([])
  let answers = $state({})
  let attempts = $state([])
  let result = $state(null)
  let error = $state('')
  let loading = $state(true)
  let step = $state(0)
  let checked = $state({})
  let next = $state(null)
  const startedAt = nowString()

  onMount(async () => {
    try {
      quiz = await call('local_quiz', { name: params.id })
      questions = quiz.question_rows.map((q) => ({ ...q, options: shuffle(q.options, q.name + startedAt) }))
      attempts = (await L.mine('quiz_attempt')).filter((a) => a.quiz === params.id)
    } catch (e) {
      error = errorText(e)
    }
    loading = false
  })

  let used = $derived(attempts.length)
  let left = $derived(quiz?.max_attempts ? Math.max(quiz.max_attempts - used, 0) : null)
  let answered = $derived(questions.filter((q) => answers[q.name]?.size).length)

  function pick(q, id) {
    if (result || checked[q.name]) return
    const multi = q.question_type === 'Multiple Correct Answer'
    const set = new Set(multi ? answers[q.name] || [] : [])
    if (multi && set.has(id)) set.delete(id)
    else set.add(id)
    answers[q.name] = set
  }

  /** Whether the learner's choice for one question is exactly the right options. */
  function isRight(q) {
    const want = q.options.filter((o) => o.is_correct).map((o) => o.id).sort().join()
    return [...(answers[q.name] || [])].sort().join() === want
  }

  async function suggestNext(score) {
    if (!params.lesson) return
    const here = await L.one('lesson', params.lesson)
    if (!here) return
    if (score < (quiz.passing_score || 50)) {
      next = { lesson: here, why: 'Read it once more, then try again: it sticks the second time.' }
      return
    }
    const done = await L.progressByLesson()
    const lessons = await L.list('lesson', here.course)
    const after = lessons.slice(lessons.findIndex((l) => l.name === here.name) + 1)
    const pick = after.find((l) => !l.locked && done[l.name]?.status !== 'Completed')
    if (pick) next = { lesson: pick, why: 'The next lesson in this learning area.' }
  }

  async function submit() {
    result = markQuiz(questions, answers)
    suggestNext(result.score)
    await queue('quiz_attempt', {
      quiz: quiz.name,
      lesson: params.lesson || null,
      answers: questions.map((q) => ({ question: q.name, selected: [...(answers[q.name] || [])] })),
      started_at: startedAt,
      completed_at: nowString(),
      score: result.score,
    })
    window.scrollTo(0, 0)
  }

  function retry() {
    answers = {}
    checked = {}
    next = null
    result = null
    step = 0
    attempts = [...attempts, {}]
    window.scrollTo(0, 0)
  }

  const optionClass = (q, o) => {
    const chosen = answers[q.name]?.has(o.id)
    if (!result && !checked[q.name]) return chosen ? 'on' : ''
    if (o.is_correct) return 'right'
    return chosen ? 'wrong' : ''
  }
</script>

<TopBar title={quiz?.title || 'Quiz'} backTo={params.lesson ? '/lesson/' + enc(params.lesson) : '/'} />
<div class="page">
  {#if loading}
    <Loading />
  {:else if error}
    <Empty icon="📶" title="Quiz not available"><p>{error}</p></Empty>
  {:else if left === 0 && !result}
    <Empty icon="🏁" title="No attempts left">
      <p>You have used all {quiz.max_attempts} attempts on this quiz. Your best score is saved.</p>
    </Empty>
  {:else}
    {#if result}
      <div class="hero center">
        <div style="font-size: 2.6rem">{result.score >= (quiz.passing_score || 50) ? '🎉' : '💪'}</div>
        <div class="stat">{Math.round(result.score)}%</div>
        <div>{result.correct} of {result.total} correct · {level(result.score)}</div>
        <div class="small muted" style="margin-top: 6px">Your teacher sees the score after your next sync.</div>
      </div>
      <div class="row wrap" style="margin-bottom: 16px">
        {#if left === null || left > 1}<button class="btn ghost" onclick={retry}>Try again</button>{/if}
        {#if params.lesson}<a class="btn ghost" href={`#/tutor?lesson=${enc(params.lesson)}`}>💬 Ask Mwalimu what I missed</a>{/if}
        <a class="btn" href="#/">Back to lessons</a>
      </div>
    {:else}
      <div class="dots" aria-label="Question {step + 1} of {questions.length}">
        {#each questions as q, i}<button class:done={answers[q.name]?.size} class:now={i === step} onclick={() => (step = i)} aria-label="Question {i + 1}"></button>{/each}
      </div>
      <div class="row between small muted" style="margin-bottom: 10px">
        <span>{answered} of {questions.length} answered</span>
        {#if left !== null}<span>{left} attempt{left === 1 ? '' : 's'} left</span>{/if}
      </div>
    {/if}

    {#each result ? questions : questions.slice(step, step + 1) as q, k (q.name)}
      {@const i = result ? k : step}
      <div class="card">
        <div class="small muted">Question {i + 1}{q.question_type === 'Multiple Correct Answer' ? ' · pick all that are right' : ''}</div>
        <div class="prose" style="font-weight: 600; margin: 6px 0 12px">{@html safeHtml(q.question)}</div>
        {#each q.options as o, j}
          <button class="option {optionClass(q, o)}" onclick={() => pick(q, o.id)} disabled={!!result || checked[q.name]}>
            <span class="mark">{String.fromCharCode(65 + j)}</span>
            <span class="grow">{o.text}</span>
          </button>
        {/each}
        {#if !result && checked[q.name]}
          <div class="verdict" class:ok={isRight(q)}>{isRight(q) ? '🎉 Correct!' : '❌ Not quite: the right answer is marked green.'}</div>
        {/if}
      </div>
    {/each}

    {#if result && next}
      <a class="card tap row learn-next" href={`#/lesson/${enc(next.lesson.name)}`}>
        <span class="today-ico">{next.lesson.name === params.lesson ? '🔁' : '➡️'}</span>
        <span class="grow"><small class="muted">{next.lesson.name === params.lesson ? 'Learn this again' : 'Learn this next'}</small><b style="display: block">{next.lesson.title}</b><small class="muted">{next.why}</small></span>
      </a>
    {/if}

    {#if !result && questions.length}
      <div class="row" style="margin-top: 16px">
        {#if step > 0}<button class="btn ghost" onclick={() => step--}>Back</button>{/if}
        {#if !checked[questions[step].name]}
          <button class="btn grow" onclick={() => (checked[questions[step].name] = true)} disabled={!answers[questions[step].name]?.size}>Check my answer</button>
        {:else if step < questions.length - 1}
          <button class="btn grow" onclick={() => step++}>Next question</button>
        {:else}
          <button class="btn grow" onclick={submit} disabled={answered < questions.length}>
            {answered < questions.length ? `Answer all ${questions.length} questions` : 'See my score'}
          </button>
        {/if}
      </div>
    {/if}
  {/if}
</div>

{#if !loading && !error && !result && questions[step] && !checked[questions[step].name]}
  <!-- A hint for this question, not its answer: the quiz still checks what the learner knows. -->
  <AskMwalimu
    href={`#/tutor?${params.lesson ? `lesson=${enc(params.lesson)}&` : ''}mode=hint&ask=${enc(`I'm stuck on this question: ${plain(questions[step].question)}`)}`}
    label="Stuck? Get a hint"
  />
{/if}

<style>
  .dots { display: flex; gap: 6px; margin-bottom: 10px; }
  .dots button { flex: 1; height: 8px; border: 0; padding: 0; border-radius: 99px; background: var(--line); cursor: pointer; }
  .dots button.done { background: var(--brand); }
  .dots button.now { background: var(--sun); }
  .verdict { margin-top: 10px; padding: 10px 12px; border-radius: 12px; font-weight: 700; background: var(--bad-soft); color: var(--bad); animation: shake 0.3s; }
  .verdict.ok { background: var(--ok-soft); color: var(--ok); animation: pop 0.3s; }
  .learn-next { gap: 12px; margin-bottom: 14px; border-left: 4px solid var(--brand); }
  @keyframes pop { 50% { transform: scale(1.04); } }
  @keyframes shake { 25% { transform: translateX(-4px); } 75% { transform: translateX(4px); } }
</style>
