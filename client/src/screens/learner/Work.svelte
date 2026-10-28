<script>
  import { onMount } from 'svelte'
  import { enc } from '../../lib/router.svelte.js'
  import { date } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'

  let items = $state([])
  let tab = $state('todo')
  let loading = $state(true)

  async function load() {
    const subs = Object.fromEntries((await L.mine('submission')).map((s) => [s.assignment, s]))
    items = (await L.mine('assignment'))
      .map((a) => ({ ...a, sub: subs[a.name] || null }))
      .sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')))
    loading = false
  }

  onMount(() => {
    load()
    window.addEventListener('cbc:synced', load)
    return () => window.removeEventListener('cbc:synced', load)
  })

  const todo = (a) => (!a.sub || a.sub.status === 'Returned' || a.sub.status === 'Not accepted') && a.status === 'Published'
  let shown = $derived(
    items.filter((a) => (tab === 'todo' ? todo(a) : tab === 'done' ? a.sub && !todo(a) : !a.sub && a.status === 'Closed')),
  )
  const overdue = (a) => a.due_date && new Date(a.due_date) < new Date(new Date().toDateString())
  const tone = (s) => ({ Reviewed: 'ok', Submitted: 'brand', Late: 'warn', Returned: 'warn', 'Not accepted': 'bad' })[s] || ''
</script>

<TopBar title="Assignments" />
<div class="page">
  <div class="tabs">
    <button class="tab" class:on={tab === 'todo'} onclick={() => (tab = 'todo')}>To do</button>
    <button class="tab" class:on={tab === 'done'} onclick={() => (tab = 'done')}>Handed in</button>
    <button class="tab" class:on={tab === 'missed'} onclick={() => (tab = 'missed')}>Closed</button>
  </div>
  {#if loading}
    <Loading />
  {:else if !shown.length}
    <Empty icon={tab === 'todo' ? '🎉' : '📭'} title={tab === 'todo' ? 'Nothing to do right now' : 'Nothing here yet'}>
      <p class="small">Assignments from your teachers appear here after you sync.</p>
    </Empty>
  {:else}
    {#each shown as a}
      <a class="card tap row" href={'#/work/' + enc(a.name)}>
        <span style="font-size: 1.5rem">{a.assignment_type === 'Project' ? '🧪' : a.assignment_type === 'Homework' ? '🏠' : '📝'}</span>
        <div class="grow">
          <b>{a.title}</b>
          <div class="small muted">
            {a.assignment_type}
            {#if a.due_date} · due {date(a.due_date)}{/if}
          </div>
        </div>
        {#if a.sub}<span class="pill {tone(a.sub.status)}">{a.sub.status}</span>
        {:else if overdue(a)}<span class="pill bad">Overdue</span>{/if}
      </a>
    {/each}
  {/if}
</div>
