<script>
  import { onMount, tick } from 'svelte'
  import { app, queue } from '../../lib/app.svelte.js'
  import { api, get, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, markdown } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let { params } = $props()
  let lesson = $state(null)
  let conversation = $state(params.conversation || null)
  let messages = $state([])
  let past = $state(null)
  let text = $state('')
  let busy = $state(false)
  let error = $state(null)
  let quota = $state(null)
  let loading = $state(true)
  let feed

  const starters = [
    'Explain this in a simpler way',
    'Give me an example from home',
    'Ask me a question to check I understand',
    'Nieleze kwa Kiswahili',
  ]

  onMount(async () => {
    if (params.lesson) lesson = await L.one('lesson', params.lesson)
    quota = (await L.status()).ai_quota
    try {
      if (conversation) {
        const rows = await get('tutor.conversation', { conversation })
        messages = rows.flatMap((r) => [
          { me: true, text: r.question },
          { me: false, text: r.answer, interaction: r.interaction, feedback: r.feedback },
        ])
      } else if (!lesson) {
        past = await get('tutor.conversations', { limit: 20 }, { cache: 'tutor:conversations' })
      }
    } catch (e) {
      error = e
    }
    loading = false
    scroll()
  })

  async function scroll() {
    await tick()
    feed?.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }

  async function send(message = text) {
    message = message.trim()
    if (!message || busy) return
    text = ''
    error = null
    messages.push({ me: true, text: message })
    busy = true
    scroll()
    try {
      const res = await api('tutor.ask', { message, conversation, lesson: lesson?.name || null })
      conversation = res.conversation
      quota = res.quota
      messages.push({ me: false, text: res.answer, interaction: res.interaction })
    } catch (e) {
      error = e
      messages.pop()
      text = message
    } finally {
      busy = false
      scroll()
    }
  }

  async function rate(m, helpful) {
    m.feedback = helpful ? 'Helpful' : 'Not helpful'
    await queue('ai_feedback', { interaction: m.interaction, helpful: helpful ? 1 : 0 })
  }

  function onkey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }
</script>

<TopBar title={lesson ? `Mwalimu · ${lesson.title}` : 'Mwalimu, your AI tutor'} backTo={lesson ? '/lesson/' + enc(lesson.name) : null}>
  {#if conversation || messages.length}
    <button class="btn sm ghost" onclick={() => go(lesson ? `/tutor?lesson=${enc(lesson.name)}&new=${Date.now()}` : `/tutor?new=${Date.now()}`)}>New chat</button>
  {/if}
</TopBar>

<div class="page" style="display: flex; flex-direction: column; min-height: calc(100vh - 70px)">
  {#if !app.online}
    <div class="banner info">📶 Mwalimu needs the internet. Your lessons and quizzes still work offline.</div>
  {/if}
  {#if quota && quota.limit}
    <div class="small muted" style="margin-bottom: 8px">{quota.remaining ?? '∞'} of {quota.limit} questions left today</div>
  {/if}

  {#if loading}
    <Loading />
  {:else if past && !messages.length}
    <Stale result={past} />
    <div class="card" style="margin-bottom: 14px">
      <h3>Hujambo! I'm Mwalimu 👋</h3>
      <p class="muted">Ask me anything about your lessons. I will help you think it through instead of just giving answers.</p>
    </div>
    {#if past.data?.length}
      <div class="section"><h2>Earlier chats</h2></div>
      {#each past.data as c}
        <a class="card tap flat row" style="margin-bottom: 8px" href={`#/tutor?conversation=${enc(c.conversation)}`}>
          <span>💬</span>
          <div class="grow"><b>{c.topic || 'Chat'}</b><div class="small muted">{c.messages} messages · {ago(c.last)}</div></div>
        </a>
      {/each}
    {/if}
  {/if}

  <div class="grow" bind:this={feed}>
    {#each messages as m}
      <div class="bubble {m.me ? 'me' : 'ai'}">
        {#if m.me}{m.text}{:else}
          <div class="prose">{@html markdown(m.text)}</div>
          {#if m.interaction}
            <div class="row small" style="margin-top: 6px; gap: 4px">
              {#if m.feedback}<span class="muted">Thanks for the feedback</span>{:else}
                <button class="icon-btn" style="width: 32px; height: 32px" aria-label="Helpful" onclick={() => rate(m, true)}>👍</button>
                <button class="icon-btn" style="width: 32px; height: 32px" aria-label="Not helpful" onclick={() => rate(m, false)}>👎</button>
              {/if}
            </div>
          {/if}
        {/if}
      </div>
    {/each}
    {#if busy}<div class="bubble ai"><span class="spinner"></span> Mwalimu is thinking…</div>{/if}
  </div>

  <ErrorBox {error} />

  {#if !messages.length && !loading}
    <div class="row wrap" style="margin: 10px 0">
      {#each lesson ? starters : starters.slice(3) as s}
        <button class="tab" onclick={() => send(lesson ? `${s} (lesson: ${lesson.title})` : s)} disabled={!app.online}>{s}</button>
      {/each}
    </div>
  {/if}

  <div class="row" style="position: sticky; bottom: calc(76px + var(--safe-bottom)); background: var(--bg); padding: 8px 0">
    <textarea rows="1" style="min-height: 46px; height: 46px" placeholder="Type your question…" bind:value={text} onkeydown={onkey} disabled={!app.online} maxlength="2000"></textarea>
    <button class="btn" onclick={() => send()} disabled={busy || !text.trim() || !app.online}>Send</button>
  </div>
  <p class="small muted center">Mwalimu can make mistakes. Check with your teacher when unsure. Feeling unsafe? Call Childline Kenya on 116 (free).</p>
</div>
