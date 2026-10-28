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

  let { params } = $props()
  let quiz = $state(null)
  let questions = $state([])
  let answers = $state({})
  let attempts = $state([])
  let result = $state(null)
  let error = $state('')
  let loading = $state(true)
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
    if (result) return
    const multi = q.question_type === 'Multiple Correct Answer'
    const set = new Set(multi ? answers[q.name] || [] : [])
    if (multi && set.has(id)) set.delete(id)
    else set.add(id)
    answers[q.name] = set
  }

  async function submit() {
    result = markQuiz(questions, answers)
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
    result = null
    attempts = [...attempts, {}]
    window.scrollTo(0, 0)
  }

  const optionClass = (q, o) => {
    const chosen = answers[q.name]?.has(o.id)
    if (!result) return chosen ? 'on' : ''
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
      <div class="row between small muted" style="margin-bottom: 10px">
        <span>{answered} of {questions.length} answered</span>
        {#if left !== null}<span>{left} attempt{left === 1 ? '' : 's'} left</span>{/if}
      </div>
    {/if}

    {#each questions as q, i}
      <div class="card">
        <div class="small muted">Question {i + 1}{q.question_type === 'Multiple Correct Answer' ? ' · pick all that are right' : ''}</div>
        <div class="prose" style="font-weight: 600; margin: 6px 0 12px">{@html safeHtml(q.question)}</div>
        {#each q.options as o, j}
          <button class="option {optionClass(q, o)}" onclick={() => pick(q, o.id)} disabled={!!result}>
            <span class="mark">{String.fromCharCode(65 + j)}</span>
            <span class="grow">{o.text}</span>
          </button>
        {/each}
      </div>
    {/each}

    {#if !result && questions.length}
      <button class="btn block" style="margin-top: 16px" onclick={submit} disabled={answered < questions.length}>
        {answered < questions.length ? `Answer all ${questions.length} questions` : 'Check my answers'}
      </button>
    {/if}
  {/if}
</div>
