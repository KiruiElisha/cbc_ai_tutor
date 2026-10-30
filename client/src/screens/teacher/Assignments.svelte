<script>
  import { onMount } from 'svelte'
  import { get } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import { date } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let { params } = $props()
  let tab = $state(params.review ? 'review' : 'Published')
  let res = $state(null)
  let error = $state(null)

  async function load() {
    error = null
    try {
      res = await get('teacher.assignments', {}, { cache: 'teacher:assignments' })
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  let shown = $derived((res?.data || []).filter((a) => (tab === 'review' ? a.to_review > 0 : a.status === tab)))
  const count = (t) => (res?.data || []).filter((a) => (t === 'review' ? a.to_review > 0 : a.status === t)).length
</script>

<TopBar title="Assignments">
  <a class="btn sm" href="#/assignment/new">+ New</a>
</TopBar>
<div class="page">
  <div class="tabs">
    {#each [['Published', 'Open'], ['review', 'To review'], ['Draft', 'Drafts'], ['Closed', 'Closed']] as [key, label]}
      <button class="tab" class:on={tab === key} onclick={() => (tab = key)}>{label}{res ? ` (${count(key)})` : ''}</button>
    {/each}
  </div>
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if res}
    {#each shown as a}
      <div class="card flat row">
        <a class="grow" href={'#/assignment/' + enc(a.name)} style="color: inherit; text-decoration: none">
          <b>{a.title}</b>
          <div class="small muted">{a.grade} · {a.assignment_type}{a.due_date ? ' · due ' + date(a.due_date) : ''}</div>
        </a>
        {#if a.status !== 'Draft'}
          <a class="btn sm ghost" href={'#/assignment/' + enc(a.name) + '/submissions'}>
            <span>{a.submitted} handed in</span>{#if a.to_review}<span class="pill warn">{a.to_review} new</span>{/if}
          </a>
        {/if}
      </div>
    {:else}
      <Empty icon="📝" title={tab === 'Draft' ? 'No drafts' : tab === 'review' ? 'Nothing to review' : 'No assignments here'}>
        {#if tab !== 'review'}<a class="btn" href="#/assignment/new">Create an assignment</a>{/if}
      </Empty>
    {/each}
  {/if}
</div>
