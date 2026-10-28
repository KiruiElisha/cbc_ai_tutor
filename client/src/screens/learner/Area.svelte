<script>
  import { onMount } from 'svelte'
  import { enc } from '../../lib/router.svelte.js'
  import * as L from '../../lib/learner.js'
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

  onMount(async () => {
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
        .filter((g) => g.lessons.length)
      const direct = lessons.filter((l) => !used.has(l.name) && l.strand === s.name)
      direct.forEach((l) => used.add(l.name))
      if (subGroups.length || direct.length) out.push({ ...s, subs: subGroups, direct })
    }
    const rest = lessons.filter((l) => !used.has(l.name))
    if (rest.length) out.push({ name: '_other', title: 'More lessons', subs: [], direct: rest })
    groups = out
    if (out[0]) open[out[0].name] = true
    loading = false
  })
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
    <Empty icon="📚" title="No lessons yet">
      <p>Your teachers are still adding lessons for {area?.title}. Check again after the next sync.</p>
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
            {/each}
            {#each g.direct as l}{@render lessonRow(l)}{/each}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>
