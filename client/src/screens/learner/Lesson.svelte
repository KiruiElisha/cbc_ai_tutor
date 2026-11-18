<script>
  import { onMount } from 'svelte'
  import { openUrl } from '@tauri-apps/plugin-opener'
  import { app, queue, toast } from '../../lib/app.svelte.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { safeHtml } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import AskMwalimu from '../../components/AskMwalimu.svelte'
  import { canSpeak, readAlong, stopSpeaking } from '../../lib/voice.js'
  import { subject } from '../../lib/subjects.js'

  let { params } = $props()
  let lesson = $state(null)
  let outcome = $state(null)
  let where = $state({ area: '', topic: '' })
  let progress = $state(null)
  let loading = $state(true)
  let started = Date.now()
  let reported = 0
  let scrolled = $state(0)
  let step = $state(0)
  let whole = $state(false)
  // Read-along: the screen's words, read aloud with the word being said lit up.
  let reading = $state(false)
  let word = $state(-1)
  let words = $state([])

  const html = (h) => safeHtml(L.absolutize(h, app.server))
  let embed = $derived(L.videoEmbed(lesson?.video_url))

  onMount(() => {
    load()
    const quiet = () => stopSpeaking()
    const onScroll = () => {
      const h = document.documentElement
      const pct = Math.round((100 * (h.scrollTop + h.clientHeight)) / Math.max(h.scrollHeight, 1))
      scrolled = Math.max(scrolled, Math.min(pct, 95))
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    const timer = setInterval(() => report(false), 120000)
    return () => {
      window.removeEventListener('scroll', onScroll)
      quiet()
      clearInterval(timer)
      report(false)
    }
  })

  async function load() {
    lesson = await L.one('lesson', params.id)
    if (lesson?.learning_outcome) outcome = await L.one('outcome', lesson.learning_outcome)
    if (lesson) {
      const [area, sub] = await Promise.all([L.one('area', lesson.course), lesson.sub_strand ? L.one('sub_strand', lesson.sub_strand) : null])
      where = { area: area?.title || '', topic: sub?.title || '' }
    }
    progress = (await L.progressByLesson())[params.id] || null
    loading = false
    if (lesson && !lesson.locked && !progress) report(false, 10)
  }

  /** Time spent and how far the learner got, queued for the next sync. */
  async function report(completed, minProgress = 0) {
    if (!lesson || lesson.locked) return
    const now = Date.now()
    const delta = Math.round((now - started) / 1000) - reported
    if (!completed && delta < 15 && !minProgress) return
    reported += Math.max(delta, 0)
    await queue('lesson_progress', {
      lesson: lesson.name,
      progress: completed ? 100 : Math.max(scrolled, minProgress, progress?.progress || 0),
      completed: completed ? 1 : 0,
      time_spent_delta: Math.max(delta, 0),
    })
  }

  /**
   * The lesson in short screens: the body split at its headings (and long stretches split at
   * paragraphs), then key words, the activity and the reflection, each on its own screen.
   */
  function screensOf(l) {
    if (!l) return []
    const out = []
    const doc = new DOMParser().parseFromString(`<div>${html(l.body || '')}</div>`, 'text/html')
    let part = []
    let size = 0
    const close = () => {
      if (part.length) out.push({ kind: 'read', html: part.map((n) => n.outerHTML || n.textContent).join('') })
      part = []
      size = 0
    }
    for (const node of doc.body.firstChild.childNodes) {
      if (node.nodeType === 3 && !node.textContent.trim()) continue
      const heading = /^H[1-4]$/.test(node.nodeName)
      const length = (node.textContent || '').length
      if ((heading && size > 0) || (size > 700 && size + length > 1100)) close()
      part.push(node.nodeType === 3 ? Object.assign(document.createElement('p'), { textContent: node.textContent }) : node)
      size += length
    }
    close()
    if (!out.length) out.push({ kind: 'read', html: '' })
    if (l.key_vocabulary) out.push({ kind: 'words', title: '📌 Key words', text: l.key_vocabulary })
    if (l.activities) out.push({ kind: 'try', title: '✋ Try this', html: html(l.activities) })
    if (l.reflection) out.push({ kind: 'think', title: '💭 Think about it', text: l.reflection })
    return out
  }
  let screens = $derived(screensOf(lesson))
  let last = $derived(step >= screens.length - 1)

  function plainOf(sc) {
    const div = document.createElement('div')
    div.innerHTML = sc.html || ''
    return ((sc.title ? sc.title + '. ' : '') + (sc.text || div.textContent || '')).replace(/\s+/g, ' ').trim()
  }

  async function readToMe() {
    if (reading) {
      stopSpeaking()
      reading = false
      word = -1
      return
    }
    const text = plainOf(screens[step])
    words = text.split(/\s+/).filter(Boolean)
    reading = true
    await readAlong(text, { onWord: (i) => (word = i) })
    reading = false
  }

  function goTo(i) {
    if (reading) {
      stopSpeaking()
      reading = false
    }
    step = Math.max(0, Math.min(i, screens.length - 1))
    // Reading on is progress, as scrolling down is on the one-page view.
    scrolled = Math.max(scrolled, Math.min(95, Math.round(((step + 1) / screens.length) * 100)))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function finish() {
    await report(true)
    progress = { ...(progress || {}), status: 'Completed', progress: 100 }
    toast('Lesson done! 🎉', 'ok')
    if (lesson.quiz) go(`/quiz/${enc(lesson.quiz)}?lesson=${enc(lesson.name)}`)
  }
</script>

<TopBar title={lesson?.title || 'Lesson'} backTo={lesson ? '/area/' + enc(lesson.course) : '/'} />
<div class="page">
  {#if loading}
    <Loading />
  {:else if !lesson}
    <Empty icon="🔍" title="Lesson not found"><p>It may have been removed. Sync to refresh your lessons.</p></Empty>
  {:else}
    {@const t = subject(where.area)}
    <header class="lesson-head" style={t.style}>
      <div class="crumb"><span class="chip">{t.icon}</span>{where.area}{#if where.topic}{' · '}{where.topic}{/if}</div>
      <h1>{lesson.title}</h1>
      <div class="row wrap small">
        {#if lesson.estimated_minutes}<span class="pill">⏱ {lesson.estimated_minutes} min</span>{/if}
        {#if progress?.status === 'Completed'}<span class="pill ok">✓ Done</span>{:else if progress}<span class="pill brand">{progress.progress || 0}% read</span>{/if}
      </div>
    </header>

    {#if outcome}
      <div class="banner info small"><div><b>You will learn to:</b> {@html safeHtml(outcome.description)}</div></div>
    {/if}

    {#if lesson.summary}<p style="font-size: 1.05rem">{lesson.summary}</p>{/if}

    {#if lesson.locked}
      <div class="card center">
        <div style="font-size: 2.4rem">🔒</div>
        <h3>This lesson is part of the family plan</h3>
        <p class="muted">Ask your parent to renew in their CBC Tutor app. Lessons marked Free still work.</p>
      </div>
    {:else}
      {#if lesson.image}<img src={L.fileUrl(lesson.image, app.server)} alt="" style="border-radius: 12px; margin-bottom: 12px" />{/if}
      {#if embed && app.online}
        <div class="prose" style="margin-bottom: 14px"><iframe src={embed} title="Lesson video" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe></div>
      {:else if lesson.video_url}
        <button class="btn ghost sm" style="margin-bottom: 14px" onclick={() => openUrl(lesson.video_url)}>▶ Watch the video {app.online ? '' : '(needs internet)'}</button>
      {/if}

      {#if whole}
        <article class="card prose">{@html html(lesson.body)}</article>
        {#if lesson.key_vocabulary}
          <div class="card"><h3>📌 Key words</h3><p style="white-space: pre-line">{lesson.key_vocabulary}</p></div>
        {/if}
        {#if lesson.activities}
          <div class="card prose"><h3>✋ Try this</h3>{@html html(lesson.activities)}</div>
        {/if}
        {#if lesson.reflection}
          <div class="card"><h3>💭 Think about it</h3><p style="white-space: pre-line">{lesson.reflection}</p></div>
        {/if}
      {:else}
        {@const sc = screens[step]}
        <div class="steps-bar" aria-label="Part {step + 1} of {screens.length}">
          {#each screens as _, i}<button class:done={i < step} class:now={i === step} onclick={() => goTo(i)} aria-label="Part {i + 1}"></button>{/each}
        </div>
        {#if canSpeak}
          <button class="btn sm ghost read-btn" class:on={reading} onclick={readToMe}>{reading ? '⏹ Stop reading' : '🔊 Read to me'}</button>
        {/if}
        {#key step}
          <article class="card prose screen screen-{sc.kind}">
            {#if reading}
              <p class="read-along">{#each words as w, i}<span class:said={i === word} class:past={i < word}>{w}</span>{' '}{/each}</p>
            {:else}
              {#if sc.title}<h3>{sc.title}</h3>{/if}
              {#if sc.html}{@html sc.html}{:else if sc.text}<p style="white-space: pre-line">{sc.text}</p>{/if}
            {/if}
          </article>
        {/key}
        <div class="row" style="margin-top: 14px">
          {#if step > 0}<button class="btn ghost" onclick={() => goTo(step - 1)}>← Back</button>{/if}
          {#if !last}<button class="btn grow" onclick={() => goTo(step + 1)}>Next ({step + 2} of {screens.length})</button>{/if}
        </div>
      {/if}
      <div class="small center" style="margin-top: 8px">
        <button class="link" onclick={() => (whole = !whole)}>{whole ? 'Show one part at a time' : 'Show the whole lesson on one page'}</button>
      </div>

      {#if whole || last}
      <div class="row wrap" style="margin-top: 18px">
        <button class="btn" onclick={finish}>{lesson.quiz ? "I'm done, take the quiz" : "I've finished this lesson"}</button>
        <a class="btn ghost" href={`#/tutor?lesson=${enc(lesson.name)}`}>💬 Ask Mwalimu</a>
        <a class="btn ghost" href={`#/practice?lesson=${enc(lesson.name)}`}>🎯 Practice</a>
      </div>
      {/if}
    {/if}
  {/if}
</div>

{#if lesson && !lesson.locked}<AskMwalimu href={`#/tutor?lesson=${enc(lesson.name)}`} />{/if}

<style>
  .lesson-head {
    margin: -4px 0 16px; padding: 16px; border-radius: 18px;
    background: linear-gradient(135deg, color-mix(in srgb, var(--c) 14%, white), white);
    border: 1px solid color-mix(in srgb, var(--c) 22%, white);
  }
  .lesson-head h1 { margin: 6px 0 10px; font-size: 1.55rem; letter-spacing: -0.01em; }
  .crumb { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; font-weight: 600; color: var(--c); }
  .steps-bar { display: flex; gap: 5px; margin-bottom: 12px; }
  .steps-bar button { flex: 1; height: 7px; border: 0; padding: 0; border-radius: 99px; background: var(--line); cursor: pointer; }
  .steps-bar button.done { background: var(--brand); }
  .steps-bar button.now { background: var(--sun); }
  .read-btn { margin-bottom: 10px; }
  .read-btn.on { background: var(--ke-red-soft); color: var(--ke-red); }
  .read-along { font-size: 1.35rem; line-height: 1.9; }
  .read-along span { border-radius: 6px; padding: 0 2px; transition: background 0.1s; }
  .read-along span.said { background: var(--sun); color: #1f1300; }
  .read-along span.past { color: var(--muted); }
  .screen { min-height: 220px; animation: slide-in 0.18s ease-out; }
  .screen-try { border-left: 4px solid var(--sun); }
  .screen-think { border-left: 4px solid var(--ke-red); }
  .screen-words { border-left: 4px solid var(--brand); }
  @keyframes slide-in { from { opacity: 0; transform: translateX(12px); } to { opacity: 1; transform: none; } }
  .crumb .chip { width: 30px; height: 30px; font-size: 1rem; margin: 0; }
</style>
