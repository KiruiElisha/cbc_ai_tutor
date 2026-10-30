<script>
  import { onMount, tick } from 'svelte'
  import { app } from '../../lib/app.svelte.js'
  import { go } from '../../lib/router.svelte.js'
  import { drill, isRight, topicsFor } from '../../lib/maths.js'
  import TopBar from '../../components/TopBar.svelte'

  /** Maths drills written on the device: no AI, no internet, endless fresh questions. */
  let { params } = $props()
  const ROUND = 10

  const grade = () => app.session?.profile?.learner?.grade || ''
  const store = () => `cbc:drill-best:${app.session?.profile?.learner?.student || 'me'}`
  let topics = $state([])
  let best = $state({})
  let questions = $state([])
  let at = $state(0)
  let typed = $state('')
  let chosen = $state(null)
  let right = $state(0)
  let input = $state()

  let q = $derived(questions[at])
  let answered = $derived(chosen !== null)
  let finished = $derived(questions.length && at >= questions.length)
  let topic = $derived(topics.find((t) => t.key === params.topic))

  onMount(() => {
    topics = topicsFor(grade())
    try {
      best = JSON.parse(localStorage.getItem(store()) || '{}')
    } catch {
      best = {}
    }
    if (params.topic) start()
  })

  function start() {
    questions = drill(grade(), params.topic, ROUND, Date.now())
    at = 0
    right = 0
    reset()
  }

  async function reset() {
    chosen = null
    typed = ''
    await tick()
    input?.focus()
  }

  function answer(value) {
    if (answered || !String(value).trim()) return
    chosen = String(value)
    if (isRight(chosen, q.answer)) right++
  }

  function next() {
    at++
    if (at >= questions.length) save()
    else reset()
  }

  function save() {
    const prev = best[params.topic] ?? 0
    if (right > prev) {
      best = { ...best, [params.topic]: right }
      try {
        localStorage.setItem(store(), JSON.stringify(best))
      } catch {}
    }
  }

  const stars = (n) => (n >= 9 ? 3 : n >= 7 ? 2 : n >= 5 ? 1 : 0)
</script>

<TopBar title={topic ? `Drill · ${topic.title}` : 'Maths drills'} backTo={params.topic ? '/drill' : '/'} />
<div class="page drill">
  {#if !params.topic}
    <div class="card intro">
      <span class="chip" style="--c: #2563eb">🧮</span>
      <div>
        <h2>Quick maths, any time</h2>
        <p class="muted">Ten questions at a time, made on your phone. Works with no internet and uses none of your Mwalimu questions.</p>
      </div>
    </div>
    <div class="subjects" style="margin-top: 14px">
      {#each topics as t}
        <button class="subject tap" style="--c: #2563eb; text-align: left; font: inherit; cursor: pointer" onclick={() => go('/drill/' + t.key)}>
          <b>{t.title}</b>
          <small>{best[t.key] != null ? `Best: ${best[t.key]} / ${ROUND} ${'⭐'.repeat(stars(best[t.key]))}` : 'Not tried yet'}</small>
        </button>
      {/each}
    </div>
  {:else if finished}
    <div class="card center result">
      <div class="stars">{'⭐'.repeat(stars(right)) || '💪'}</div>
      <div class="stat">{right} / {questions.length}</div>
      <p class="muted">{right === questions.length ? 'Perfect score! Hongera!' : right >= 7 ? 'Great work! Try again to beat it.' : 'Good practice. Every round makes you faster.'}</p>
      <div class="row wrap" style="justify-content: center">
        <button class="btn" onclick={start}>New round</button>
        <a class="btn ghost" href="#/drill">Other topics</a>
      </div>
    </div>
  {:else if q}
    <div class="dots" aria-label="Question {at + 1} of {questions.length}">
      {#each questions as _, i}<i class:done={i < at} class:now={i === at}></i>{/each}
    </div>
    <div class="card question">
      <div class="small muted">Question {at + 1} of {questions.length}</div>
      <div class="prompt">{q.prompt}</div>

      {#if q.options}
        <div class="choices">
          {#each q.options as o}
            <button
              class="option choice {answered ? (isRight(o, q.answer) ? 'right' : chosen === o ? 'wrong' : '') : ''}"
              onclick={() => answer(o)}
              disabled={answered}
            >{o}</button>
          {/each}
        </div>
      {:else}
        <form class="row" onsubmit={(e) => (e.preventDefault(), answer(typed))}>
          <input bind:this={input} bind:value={typed} inputmode="text" placeholder="Your answer, e.g. 3/4" disabled={answered} />
          <button class="btn" disabled={answered || !typed.trim()}>Check</button>
        </form>
      {/if}

      {#if answered}
        <div class="banner {isRight(chosen, q.answer) ? 'ok' : 'bad'}" style="margin: 14px 0 0">
          {isRight(chosen, q.answer) ? '✅ Correct!' : `❌ The answer is ${q.answer}.`} {q.why}
        </div>
        <button class="btn block" style="margin-top: 12px" onclick={next}>{at + 1 < questions.length ? 'Next question' : 'See my score'}</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .intro { display: flex; gap: 14px; align-items: flex-start; }
  .intro .chip { flex-shrink: 0; margin: 0; }
  .question { padding: 22px; }
  .prompt { font-size: 1.7rem; font-weight: 800; margin: 8px 0 18px; letter-spacing: -0.01em; }
  .choices { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .choice { justify-content: center; font-size: 1.25rem; font-weight: 700; min-height: 62px; margin: 0; align-items: center; }
  .dots { display: flex; gap: 6px; margin-bottom: 12px; }
  .dots i { flex: 1; height: 6px; border-radius: 99px; background: var(--line); }
  .dots i.done { background: var(--brand); }
  .dots i.now { background: var(--sun); }
  .result { padding: 30px 20px; }
  .stars { font-size: 2.6rem; }
  .result .stat { font-size: 2.4rem; }
</style>
