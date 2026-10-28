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

  let { params } = $props()
  let lesson = $state(null)
  let outcome = $state(null)
  let progress = $state(null)
  let loading = $state(true)
  let started = Date.now()
  let reported = 0
  let scrolled = $state(0)

  const html = (h) => safeHtml(L.absolutize(h, app.server))
  let embed = $derived(L.videoEmbed(lesson?.video_url))

  onMount(() => {
    load()
    const onScroll = () => {
      const h = document.documentElement
      const pct = Math.round((100 * (h.scrollTop + h.clientHeight)) / Math.max(h.scrollHeight, 1))
      scrolled = Math.max(scrolled, Math.min(pct, 95))
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    const timer = setInterval(() => report(false), 120000)
    return () => {
      window.removeEventListener('scroll', onScroll)
      clearInterval(timer)
      report(false)
    }
  })

  async function load() {
    lesson = await L.one('lesson', params.id)
    if (lesson?.learning_outcome) outcome = await L.one('outcome', lesson.learning_outcome)
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
    <h1>{lesson.title}</h1>
    <div class="row wrap small muted" style="margin-bottom: 12px">
      {#if lesson.estimated_minutes}<span>⏱ {lesson.estimated_minutes} min</span>{/if}
      {#if progress?.status === 'Completed'}<span class="pill ok">Done</span>{/if}
    </div>

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

      <div class="row wrap" style="margin-top: 18px">
        <button class="btn" onclick={finish}>{lesson.quiz ? "I'm done, take the quiz" : "I've finished this lesson"}</button>
        <a class="btn ghost" href={`#/tutor?lesson=${enc(lesson.name)}`}>💬 Ask Mwalimu</a>
        <a class="btn ghost" href={`#/practice?lesson=${enc(lesson.name)}`}>🎯 Practice</a>
      </div>
    {/if}
  {/if}
</div>
