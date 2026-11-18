<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import { app, queue, toast } from '../../lib/app.svelte.js'
  import { api, get } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { ago, tutorHtml } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import { solve } from '../../lib/maths.js'
  import { canListen, canSpeak, listen, speak, stopSpeaking, looksSwahili } from '../../lib/voice.js'
  import { shrinkPhoto } from '../../lib/photo.js'
  import TopBar from '../../components/TopBar.svelte'
  import Mwalimu from '../../components/Mwalimu.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'

  let { params } = $props()
  let lesson = $state(null)
  let conversation = $state(params.conversation || null)
  let messages = $state([])
  let past = $state(null)
  let text = $state(params.ask || '')
  let busy = $state(false)
  let waited = $state(0)
  let draft = $state('')
  let photo = $state(null)
  let picker
  let error = $state(null)
  let quota = $state(null)
  let loading = $state(true)
  let showModes = $state(false)
  let mode = $state(['hint', 'steps', 'simple', 'quiz', 'check', 'kiswahili'].includes(params.mode) ? params.mode : null)
  let listening = $state(false)
  let speaking = $state(null)
  let readAloud = $state(load('cbc:tutor:read_aloud') === '1')
  let lang = $state(load('cbc:tutor:voice_lang') || 'en-KE')
  let feed
  let box
  let timer
  let stopListening = null
  let spokenQuestion = false

  function load(key) {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  }
  function keep(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      /* private window: the setting lasts this visit */
    }
  }

  const firstName = $derived(app.session?.profile?.learner?.first_name || '')

  // How Mwalimu answers the next question: one at a time, and it stays on until changed.
  const modes = [
    ['hint', '💡', 'Just a hint'],
    ['steps', '🪜', 'Step by step'],
    ['simple', '🧒🏾', 'Simpler'],
    ['quiz', '❓', 'Quiz me'],
    ['check', '✅', 'Check my work'],
    ['kiswahili', '🇰🇪', 'Kiswahili'],
  ]

  const ideas = $derived(
    lesson
      ? [
          ['📖', 'Explain this lesson simply', 'simple'],
          ['🏡', 'Give me an example from home', null],
          ['❓', 'Ask me questions to check I understand', 'quiz'],
          ['🇰🇪', 'Nieleze somo hili kwa Kiswahili', 'kiswahili'],
        ]
      : [
          ['🔢', 'Help me understand fractions', 'steps'],
          ['🌱', 'Why do plants need sunlight?', null],
          ['✍🏾', 'Help me plan a composition about my county', 'hint'],
          ['🇰🇪', 'Nieleze maana ya methali "Haraka haraka haina baraka"', 'kiswahili'],
        ],
  )

  // After an answer: the next step a good tutor would offer.
  const followUps = [
    ['Explain it more simply', 'simple'],
    ['Give me a practice question', 'quiz'],
    ['Show me step by step', 'steps'],
    ['Nieleze kwa Kiswahili', 'kiswahili'],
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
      }
    } catch (e) {
      error = e
    }
    loading = false
    scroll()
    if (text) {
      // A question handed over from a quiz or lesson: show all of it, ready to send or edit.
      await tick()
      grow()
      box?.focus()
    }
    // Earlier chats: the welcome screen on phones, the side panel on wide screens.
    if (!lesson) {
      get('tutor.conversations', { limit: 20 }, { cache: 'tutor:conversations' })
        .then((r) => (past = r))
        .catch(() => {})
    }
  })

  onDestroy(() => {
    clearInterval(timer)
    stopListening?.()
    stopSpeaking()
  })

  async function scroll() {
    await tick()
    feed?.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }

  function grow() {
    if (!box) return
    box.style.height = 'auto'
    box.style.height = Math.min(box.scrollHeight, 160) + 'px'
  }

  async function pickPhoto(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try {
      photo = await shrinkPhoto(file)
      box?.focus()
    } catch (err) {
      toast(err.message || 'That photo could not be used.', 'error')
    }
  }

  async function send(message = text, style = mode) {
    message = message.trim()
    const sentPhoto = photo
    if ((!message && !sentPhoto) || busy) return
    if (sentPhoto && !app.online) {
      toast('Photos need the internet. Type the question to work out sums offline.', 'error')
      return
    }
    photo = null
    stopListening?.()
    stopSpeaking()
    text = ''
    error = null
    await tick()
    grow()
    const spoken = spokenQuestion
    spokenQuestion = false
    messages.push({ me: true, text: message, mode: style, photo: sentPhoto?.preview })
    // Sums are worked out on the device: instant, offline, and no tutor question used.
    const sum = sentPhoto ? null : solve(message)
    if (sum) {
      messages.push({ me: false, text: sum.markdown, local: true })
      scroll()
      return
    }
    if (!app.online) {
      messages.push({ me: false, text: 'I need the internet to answer that. I can still work out sums offline, like **3/4 + 1/2** or **25% of 200**.', local: true })
      scroll()
      return
    }
    busy = true
    waited = 0
    timer = setInterval(() => waited++, 1000)
    scroll()
    const styles = [style, spoken && readAloud ? 'voice' : null].filter(Boolean).join(',')
    // The answer appears as it is written: the server keeps the text so far, and we ask for it
    // twice a second until the full answer comes back.
    const stream = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).slice(0, 36)
    draft = ''
    let polling = true
    const poll = async () => {
      while (polling) {
        await new Promise((r) => setTimeout(r, 500))
        if (!polling) break
        try {
          const part = await get('tutor.partial', { stream })
          if (polling && part?.text && part.text.length > draft.length) {
            draft = part.text
            scroll()
          }
        } catch {
          /* the full answer still comes back from ask */
        }
      }
    }
    poll()
    try {
      const res = await api('tutor.ask', {
        message,
        conversation,
        lesson: lesson?.name || null,
        style: styles || null,
        stream,
        image: sentPhoto?.dataUrl || null,
      })
      polling = false
      conversation = res.conversation
      quota = res.quota
      const reply = { me: false, text: res.answer, interaction: res.interaction }
      messages.push(reply)
      if (readAloud) say(messages[messages.length - 1])
    } catch (e) {
      error = e
      messages.pop()
      text = message
      photo = sentPhoto
    } finally {
      polling = false
      draft = ''
      busy = false
      clearInterval(timer)
      scroll()
    }
  }

  async function say(m) {
    if (speaking === m) {
      stopSpeaking()
      speaking = null
      return
    }
    speaking = m
    await speak(m.text, { lang: looksSwahili(m.text) ? 'sw-KE' : lang })
    if (speaking === m) speaking = null
  }

  function mic() {
    if (listening) {
      stopListening?.()
      return
    }
    stopSpeaking()
    const before = text ? text.trim() + ' ' : ''
    listening = true
    stopListening = listen({
      lang,
      onText: (heard) => {
        text = before + heard
        grow()
      },
      onEnd: () => {
        listening = false
        stopListening = null
        // A spoken question goes straight away, as in a conversation.
        if (text.trim() && text.trim() !== before.trim()) {
          spokenQuestion = true
          send()
        }
      },
      onError: (message) => {
        listening = false
        toast(message, 'error')
      },
    })
  }

  function toggleRead() {
    readAloud = !readAloud
    keep('cbc:tutor:read_aloud', readAloud ? '1' : '0')
    if (!readAloud) stopSpeaking()
    toast(readAloud ? 'Mwalimu will read answers aloud.' : 'Reading aloud is off.', 'info')
  }

  function toggleLang() {
    lang = lang === 'en-KE' ? 'sw-KE' : 'en-KE'
    keep('cbc:tutor:voice_lang', lang)
  }

  async function copy(m) {
    try {
      await navigator.clipboard.writeText(m.text)
      toast('Copied', 'ok')
    } catch {
      toast('Could not copy on this device.', 'error')
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

  function newChat() {
    stopSpeaking()
    go(lesson ? `/tutor?lesson=${enc(lesson.name)}&new=${Date.now()}` : `/tutor?new=${Date.now()}`)
  }

  const thinking = $derived(
    waited < 4 ? 'Mwalimu is thinking' : waited < 10 ? 'Working it out carefully' : 'Almost there, thanks for waiting',
  )
  const last = $derived(messages[messages.length - 1])
  const quotaPercent = $derived(quota?.limit ? Math.max(0, Math.min(100, ((quota.remaining ?? 0) / quota.limit) * 100)) : 100)
</script>

<TopBar title={lesson ? `Mwalimu · ${lesson.title}` : 'Mwalimu, your AI tutor'} backTo={lesson ? '/lesson/' + enc(lesson.name) : null}>
  {#if canSpeak}
    <button class="icon-btn" class:lit={readAloud} aria-pressed={readAloud} title={readAloud ? 'Reading answers aloud' : 'Read answers aloud'} aria-label="Read answers aloud" onclick={toggleRead}>{readAloud ? '🔊' : '🔈'}</button>
  {/if}
  {#if conversation || messages.length}
    <button class="btn sm ghost" onclick={newChat}>New chat</button>
  {/if}
</TopBar>

<div class="tutor">
  <section class="tutor-chat">
    {#if lesson}
      <!-- What Mwalimu is focused on, so the learner knows why answers stay on this lesson. -->
      <div class="context-chip">
        <span>📌 Talking about <b>{lesson.title}</b></span>
        <a href={`#/lesson/${enc(lesson.name)}`} class="small">Open lesson</a>
        <a href={`#/tutor?new=${Date.now()}`} class="small muted" aria-label="Talk about anything">✕</a>
      </div>
    {/if}
    {#if !app.online}
      <div class="banner info">📶 You are offline. Mwalimu can still work out sums; other questions need the internet.</div>
    {/if}

    {#if loading}
      <Loading />
    {:else if !messages.length}
      <div class="tutor-hello">
        <div class="mwalimu-face"><Mwalimu size={62} mood="happy" /></div>
        <div>
          <h2>Hujambo{firstName ? `, ${firstName}` : ''}! I'm Mwalimu</h2>
          <p class="muted">Ask me about any lesson. I'll help you think it through, one step at a time{canListen ? ', and you can talk to me too' : ''}.</p>
        </div>
      </div>
      <div class="ideas">
        {#each ideas as [icon, idea, style]}
          <button class="idea" onclick={() => send(lesson && !style ? `${idea} (lesson: ${lesson.title})` : idea, style)} disabled={!app.online || busy}>
            <span class="idea-icon">{icon}</span><span>{idea}</span>
          </button>
        {/each}
      </div>
      {#if past?.data?.length}
        <div class="section show-narrow"><h2>Earlier chats</h2></div>
        <div class="show-narrow">
          {#each past.data.slice(0, 5) as c}
            <a class="past" href={`#/tutor?conversation=${enc(c.conversation)}`}>
              <span class="past-dot">💬</span>
              <span class="grow"><b>{c.topic || 'Chat'}</b><small>{c.messages} {c.messages === 1 ? 'message' : 'messages'} · {ago(c.last)}</small></span>
              <span class="muted">›</span>
            </a>
          {/each}
        </div>
      {/if}
    {/if}

    <div class="feed" bind:this={feed} aria-live="polite">
      {#each messages as m}
        <div class="msg {m.me ? 'me' : 'ai'}">
          {#if !m.me}<div class="msg-face"><Mwalimu size={32} /></div>{/if}
          <div class="bubble {m.me ? 'me' : 'ai'}">
            {#if m.me}
              {#if m.mode}<span class="mode-tag">{modes.find((x) => x[0] === m.mode)?.[2]}</span>{/if}
              {#if m.photo}<img class="sent-photo" src={m.photo} alt="What you sent" />{/if}
              {m.text}
            {:else}
              <div class="prose">{@html tutorHtml(m.text)}</div>
              {#if m.local}<div class="small muted" style="margin-top: 4px">🧮 Worked out on your device</div>{/if}
              <div class="msg-tools">
                {#if canSpeak}
                  <button class="tool" onclick={() => say(m)} aria-label={speaking === m ? 'Stop reading' : 'Read aloud'}>{speaking === m ? '⏹ Stop' : '🔈 Listen'}</button>
                {/if}
                <button class="tool" onclick={() => copy(m)} aria-label="Copy">⧉ Copy</button>
                {#if m.interaction}
                  {#if m.feedback}<span class="small muted">Thanks!</span>{:else}
                    <button class="tool" aria-label="Helpful" onclick={() => rate(m, true)}>👍</button>
                    <button class="tool" aria-label="Not helpful" onclick={() => rate(m, false)}>👎</button>
                  {/if}
                {/if}
              </div>
            {/if}
          </div>
        </div>
      {/each}
      {#if busy}
        <div class="msg ai">
          <div class="msg-face"><Mwalimu size={32} mood="think" /></div>
          {#if draft}
            <div class="bubble ai"><div class="prose">{@html tutorHtml(draft)}</div><span class="caret" aria-hidden="true"></span></div>
          {:else}
            <div class="bubble ai thinking"><span class="dots"><i></i><i></i><i></i></span> {thinking}{waited > 2 ? ` · ${waited}s` : '…'}</div>
          {/if}
        </div>
      {/if}
    </div>

    {#if last && !last.me && !busy && !last.local && app.online}
      <div class="chips" aria-label="Ask next">
        {#each followUps as [label, style]}
          <button class="chip-btn" onclick={() => send(label, style)}>{label}</button>
        {/each}
      </div>
    {/if}

    <ErrorBox {error} />

    <div class="composer-wrap">
      <button class="modes-toggle" onclick={() => (showModes = !showModes)} aria-expanded={showModes}>
        {mode ? `${modes.find((x) => x[0] === mode)[1]} ${modes.find((x) => x[0] === mode)[2]}` : '💡 How should I help?'} <span class="muted">{showModes ? '▴' : '▾'}</span>
      </button>
      <div class="modes" class:open={showModes} role="group" aria-label="How Mwalimu answers">
        {#each modes as [key, icon, label]}
          <button class="mode" class:on={mode === key} aria-pressed={mode === key} onclick={() => { mode = mode === key ? null : key; showModes = false }}>{icon} {label}</button>
        {/each}
      </div>
      {#if photo}
        <div class="photo-chip">
          <img src={photo.preview} alt="Ready to send" />
          <span class="grow small">Photo ready. Add a question, or just send it.</span>
          <button class="tool" onclick={() => (photo = null)} aria-label="Remove photo">✕</button>
        </div>
      {/if}
      <div class="composer" class:listening>
        <input bind:this={picker} type="file" accept="image/*" capture="environment" onchange={pickPhoto} hidden />
        <button class="round cam" onclick={() => picker.click()} disabled={busy || !app.online} aria-label="Ask with a photo" title="Ask with a photo">📷</button>
        <textarea
          rows="1"
          bind:this={box}
          bind:value={text}
          oninput={grow}
          onkeydown={onkey}
          maxlength="2000"
          placeholder={listening ? 'Listening… speak now' : mode === 'check' ? 'Paste your answer or working…' : 'Ask Mwalimu anything…'}
          aria-label="Your question"
        ></textarea>
        {#if canListen}
          <button class="lang" onclick={toggleLang} title="Voice language" aria-label="Voice language">{lang === 'en-KE' ? 'EN' : 'SW'}</button>
          <button class="round mic" class:on={listening} onclick={mic} disabled={!app.online || busy} aria-label={listening ? 'Stop listening' : 'Speak your question'}>{listening ? '■' : '🎤'}</button>
        {/if}
        <button class="round send" onclick={() => send()} disabled={busy || (!text.trim() && !photo)} aria-label="Send">➤</button>
      </div>
      <div class="composer-foot">
        {#if quota && quota.limit}
          <span class="quota" title="Questions left today"><i style="width: {quotaPercent}%"></i></span>
          <span>{quota.remaining ?? '∞'} of {quota.limit} questions left today</span>
        {/if}
        <span class="grow"></span>
        <span class="hide-sm">Mwalimu can make mistakes. Feeling unsafe? Call Childline Kenya on 116 (free).</span>
        <span class="show-sm">Feeling unsafe? Call 116 (free)</span>
      </div>
    </div>
  </section>

  {#if past?.data?.length}
    <aside class="tutor-side" aria-label="Earlier chats">
      <h3>Earlier chats</h3>
      {#each past.data as c}
        <a class="past" class:on={c.conversation === conversation} href={`#/tutor?conversation=${enc(c.conversation)}`}>
          <span class="grow"><b>{c.topic || 'Chat'}</b><small>{c.messages} {c.messages === 1 ? 'message' : 'messages'} · {ago(c.last)}</small></span>
        </a>
      {/each}
      <p class="small muted" style="margin-top: 14px">Feeling unsafe or upset? Talk to a parent or teacher, or call Childline Kenya on <b>116</b> (free).</p>
    </aside>
  {/if}
</div>
