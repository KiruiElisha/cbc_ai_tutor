<script>
  import { onMount } from 'svelte'
  import { enc, go } from '../../lib/router.svelte.js'
  import * as L from '../../lib/learner.js'
  import { api, errorText, isOffline } from '../../lib/tauri.js'
  import { app, syncNow, toast } from '../../lib/app.svelte.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'

  let { params } = $props()
  let area = $state(null)
  let groups = $state([])
  let done = $state({})
  let scores = $state({})
  let open = $state({})
  let loading = $state(true)
  let asking = $state(null)

  // Every strand and sub-strand of the curriculum shows, lessons or not: a topic nobody has written
  // a lesson for yet can be asked for (sync.request_lesson), and is written once for the whole grade.
  async function load() {
    area = await L.one('area', params.course)
    const [strands, lessons] = await Promise.all([L.list('strand', params.course), L.list('lesson', params.course)])
    done = await L.progressByLesson()
    scores = await L.bestScores()
    const out = []
    const used = new Set()
    for (const s of strands) {
      const subs = await L.list('sub_strand', s.name)
      const subGroups = subs
        .map((ss) => {
          const ls = lessons.filter((l) => l.sub_strand === ss.name)
          ls.forEach((l) => used.add(l.name))
          return { ...ss, lessons: ls }
        })
      const direct = lessons.filter((l) => !used.has(l.name) && l.strand === s.name)
      direct.forEach((l) => used.add(l.name))
      if (subGroups.length || direct.length) out.push({ ...s, subs: subGroups, direct })
    }
    const rest = lessons.filter((l) => !used.has(l.name))
    if (rest.length) out.push({ name: '_other', title: 'More lessons', subs: [], direct: rest })
    groups = out
    if (out[0] && !Object.keys(open).length) open[out[0].name] = true
    loading = false
  }

  onMount(load)

  async function askFor(ss) {
    if (!app.online) return toast('Connect to the internet to get this lesson.', 'error')
    asking = ss.name
    try {
      const r = await api('sync.request_lesson', { sub_strand: ss.name })
      await syncNow({ quiet: true })
      await load()
      if (r?.lesson) go('/lesson/' + enc(r.lesson))
    } catch (e) {
      toast(isOffline(e) ? 'Connect to the internet to get this lesson.' : errorText(e), 'error')
    } finally {
      asking = null
    }
  }
</script>

{#snippet lessonRow(l)}
  {@const p = done[l.name]}
  <a class="card tap flat row" href={'#/lesson/' + enc(l.name)} style="margin-bottom: 8px">
    <span style="font-size: 1.3rem">{l.locked ? '🔒' : p?.status === 'Completed' ? '✅' : p ? '🟡' : '📄'}</span>
    <div class="grow">
      <b>{l.title}</b>
      <div class="small muted">
        {l.estimated_minutes ? `${l.estimated_minutes} min` : ''}
        {#if l.quiz && scores[l.quiz] != null} · Quiz {Math.round(scores[l.quiz])}%{/if}
        {#if l.is_free && l.locked === 0}<span class="pill brand" style="margin-left: 6px">Free</span>{/if}
      </div>
    </div>
  </a>
{/snippet}

<TopBar title={area?.title || 'Learning area'} backTo="/" />
<div class="page">
  {#if loading}
    <Loading />
  {:else if !groups.length}
    <Empty icon="📚" title="No topics yet">
      <p>The curriculum for {area?.title} isn't on this device yet. Sync, then check again.</p>
    </Empty>
  {:else}
    {#if area?.description}<p class="muted">{area.description}</p>{/if}
    {#each groups as g}
      <div class="card" style="margin-bottom: 12px">
        <button class="row between" style="width: 100%; background: none; border: 0; padding: 0; cursor: pointer; font: inherit; color: inherit; text-align: left" onclick={() => (open[g.name] = !open[g.name])}>
          <h3 style="margin: 0">{g.title}</h3>
          <span>{open[g.name] ? '▾' : '▸'}</span>
        </button>
        {#if open[g.name]}
          <div style="margin-top: 12px">
            {#each g.subs as ss}
              <div class="small muted" style="font-weight: 600; margin: 10px 0 6px">{ss.title}</div>
              {#each ss.lessons as l}{@render lessonRow(l)}{/each}
              {#if !ss.lessons.length}
                <div class="card flat row" style="margin-bottom: 8px">
                  <span style="font-size: 1.3rem">✨</span>
                  <div class="grow small muted">No lesson yet for this topic.</div>
                  <button class="btn sm" disabled={!!asking} onclick={() => askFor(ss)}>
                    {asking === ss.name ? 'Writing… (about a minute)' : 'Get this lesson'}
                  </button>
                </div>
              {/if}
            {/each}
            {#each g.direct as l}{@render lessonRow(l)}{/each}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>
