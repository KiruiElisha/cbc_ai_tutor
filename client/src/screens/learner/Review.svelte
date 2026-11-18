<script>
  import { onMount } from 'svelte'
  import { app } from '../../lib/app.svelte.js'
  import { safeHtml } from '../../lib/format.js'
  import { shuffle } from '../../lib/quiz.js'
  import { due, mark } from '../../lib/review.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import AskMwalimu from '../../components/AskMwalimu.svelte'
  import { enc } from '../../lib/router.svelte.js'
  import { plain } from '../../lib/format.js'

  let questions = $state(null)
  let step = $state(0)
  let chosen = $state(null)
  let right = $state(0)
  const student = app.session?.profile?.learner?.student

  onMount(async () => {
    const { questions: qs } = await due(student)
    questions = qs.map((q) => ({ ...q, options: shuffle(q.options, q.name + new Date().toDateString()) }))
  })

  let q = $derived(questions?.[step])
  let finished = $derived(questions && step >= questions.length)

  function pick(o) {
    if (chosen) return
    chosen = o
    const ok = !!o.is_correct
    if (ok) right++
    mark(student, q.name, ok)
  }

  function next() {
    chosen = null
    step++
  }

  const cls = (o) => (!chosen ? '' : o.is_correct ? 'right' : o === chosen ? 'wrong' : '')
</script>

<TopBar title="Today's practice" backTo="/" />
<div class="page" style="max-width: 720px">
  {#if !questions}
    <Loading />
  {:else if !questions.length}
    <Empty icon="🌟" title="All caught up!">
      <p>Questions from your quizzes come back here on the right day to help you remember. Take a quiz to add more.</p>
      <a class="btn" href="#/">Back to lessons</a>
    </Empty>
  {:else if finished}
    <div class="hero center">
      <div style="font-size: 2.6rem">{right === questions.length ? '🏆' : '💪'}</div>
      <div class="stat">{right} of {questions.length}</div>
      <div>{right === questions.length ? 'Perfect! These come back later to stay fresh.' : 'The ones you missed come back tomorrow.'}</div>
    </div>
    <a class="btn block" href="#/">Done</a>
  {:else}
    <div class="steps-line small muted">Question {step + 1} of {questions.length}</div>
    <div class="bar" style="margin-bottom: 14px"><i style="width: {(100 * step) / questions.length}%"></i></div>
    <div class="card">
      <div class="prose" style="font-weight: 600; margin-bottom: 12px">{@html safeHtml(q.question)}</div>
      {#each q.options as o, j}
        <button class="option {cls(o)}" onclick={() => pick(o)} disabled={!!chosen}>
          <span class="mark">{String.fromCharCode(65 + j)}</span><span class="grow">{o.text}</span>
          {#if chosen && o.is_correct}<span aria-hidden="true">✓</span>{/if}
        </button>
      {/each}
      {#if chosen}
        <div class="feedback {chosen.is_correct ? 'ok' : 'bad'}">
          {chosen.is_correct ? '🎉 Correct!' : '❌ Not quite. The right answer is marked.'}
        </div>
        <button class="btn block" style="margin-top: 12px" onclick={next}>{step < questions.length - 1 ? 'Next question' : 'See how I did'}</button>
      {/if}
    </div>
    {#if chosen && !chosen.is_correct}
      <AskMwalimu href={`#/tutor?mode=steps&ask=${enc(`Help me understand why the answer to this is right: ${plain(q.question)}`)}`} label="Why? Ask Mwalimu" />
    {/if}
  {/if}
</div>

<style>
  .feedback { margin-top: 10px; padding: 10px 12px; border-radius: 12px; font-weight: 700; }
  .feedback.ok { background: var(--ok-soft); color: var(--ok); }
  .feedback.bad { background: var(--bad-soft); color: var(--bad); }
</style>
