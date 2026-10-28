<script>
  import { onMount } from 'svelte'
  import { app, queue } from '../../lib/app.svelte.js'
  import { api } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'

  let { params } = $props()
  let lesson = $state(null)
  let set = $state(null)
  let picked = $state([])
  let checked = $state(false)
  let busy = $state(false)
  let error = $state(null)

  onMount(async () => {
    if (params.lesson) lesson = await L.one('lesson', params.lesson)
  })

  async function make() {
    busy = true
    error = null
    try {
      set = await api('tutor.practice', { lesson: lesson?.name, count: 5 })
      picked = set.questions.map(() => -1)
      checked = false
    } catch (e) {
      error = e
    } finally {
      busy = false
    }
  }

  async function check() {
    checked = true
    await queue('practice_answers', { practice: set.practice, answers: picked })
    window.scrollTo(0, 0)
  }

  let score = $derived(set ? set.questions.filter((q, i) => q.answer === picked[i]).length : 0)
</script>

<TopBar title="Practice" backTo={lesson ? '/lesson/' + enc(lesson.name) : '/'} />
<div class="page">
  {#if !set}
    <div class="card center">
      <div style="font-size: 2.4rem">🎯</div>
      <h2>Practice questions</h2>
      <p class="muted">Mwalimu writes fresh questions on {lesson ? lesson.title : 'this topic'}, then explains each answer.</p>
      {#if !app.online}<div class="banner info">📶 Making new questions needs the internet.</div>{/if}
      <ErrorBox {error} />
      <button class="btn" onclick={make} disabled={busy || !app.online || !lesson}>{busy ? 'Writing questions…' : 'Make 5 questions'}</button>
      {#if !lesson}<p class="small muted" style="margin-top: 10px">Open a lesson and tap Practice to choose the topic.</p>{/if}
    </div>
    {#if busy}<Loading />{/if}
  {:else}
    {#if checked}
      <div class="hero center">
        <div class="stat">{score} / {set.questions.length}</div>
        <div>{score === set.questions.length ? 'Perfect! 🎉' : 'Read the explanations below 👇'}</div>
      </div>
    {/if}
    <h2>{set.title}</h2>
    {#each set.questions as q, i}
      <div class="card">
        <div style="font-weight: 600; margin-bottom: 10px">{i + 1}. {q.question}</div>
        {#each q.options as o, j}
          <button
            class="option {checked ? (j === q.answer ? 'right' : picked[i] === j ? 'wrong' : '') : picked[i] === j ? 'on' : ''}"
            onclick={() => !checked && (picked[i] = j)}
            disabled={checked}
          >
            <span class="mark">{String.fromCharCode(65 + j)}</span><span class="grow">{o}</span>
          </button>
        {/each}
        {#if checked && q.explanation}<div class="banner info small">💡 {q.explanation}</div>{/if}
      </div>
    {/each}
    {#if !checked}
      <button class="btn block" style="margin-top: 14px" onclick={check} disabled={picked.includes(-1)}>Check answers</button>
    {:else}
      <div class="row wrap" style="margin-top: 14px">
        <button class="btn" onclick={make} disabled={busy || !app.online}>{busy ? 'Writing…' : 'New questions'}</button>
        <a class="btn ghost" href={lesson ? '#/lesson/' + enc(lesson.name) : '#/'}>Back to the lesson</a>
      </div>
    {/if}
  {/if}
</div>
