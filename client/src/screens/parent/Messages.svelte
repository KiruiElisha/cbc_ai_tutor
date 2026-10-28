<script>
  import { onMount } from 'svelte'
  import { get } from '../../lib/tauri.js'
  import { date } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let res = $state(null)
  let error = $state(null)

  async function load() {
    error = null
    try {
      res = await get('parent.feedback', {}, { cache: 'parent:feedback' })
    } catch (e) {
      error = e
    }
  }
  onMount(load)
</script>

<TopBar title="Messages" />
<div class="page">
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if res}
    {#each res.data as m}
      <div class="card">
        <div class="row between small muted"><span>About <b>{m.student_name}</b></span><span>{date(m.date)}</span></div>
        <div class="bubble me" style="margin: 8px 0">{m.feedback}</div>
        {#if m.response}
          <div class="bubble ai">{m.response}</div>
        {:else}
          <div class="small muted">Waiting for a reply from the school.</div>
        {/if}
      </div>
    {:else}
      <Empty icon="✉️" title="No messages yet">
        <p>Open a child's progress and choose <b>Message the school</b> to write to their teachers.</p>
      </Empty>
    {/each}
  {/if}
</div>
