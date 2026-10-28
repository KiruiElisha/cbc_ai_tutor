<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import { date } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'

  let unanswered = $state(true)
  let res = $state(null)
  let error = $state(null)
  let replies = $state({})
  let busy = $state(null)

  async function load() {
    error = null
    try {
      res = await get('teacher.feedback', { unanswered: unanswered ? 1 : 0 }, { cache: 'teacher:feedback:' + (unanswered ? 1 : 0) })
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  async function reply(m) {
    busy = m.name
    try {
      await api('teacher.respond_feedback', { name: m.name, response: replies[m.name] })
      m.response = replies[m.name]
      delete replies[m.name]
      toast('Reply sent to the parent.', 'ok')
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      busy = null
    }
  }
</script>

<TopBar title="Parent messages" />
<div class="page">
  <div class="tabs">
    <button class="tab" class:on={unanswered} onclick={() => { unanswered = true; load() }}>Waiting for reply</button>
    <button class="tab" class:on={!unanswered} onclick={() => { unanswered = false; load() }}>All</button>
  </div>
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if res}
    {#each res.data as m}
      <div class="card">
        <div class="row between small muted">
          <span><b>{m.parent_name || 'Parent'}</b> about <a href={'#/student/' + enc(m.student)}>{m.student_name}</a></span>
          <span>{date(m.date)}</span>
        </div>
        <div class="bubble ai" style="margin: 8px 0">{m.feedback}</div>
        {#if m.response}
          <div class="bubble me">{m.response}</div>
        {:else}
          <textarea bind:value={replies[m.name]} placeholder="Write a reply…" maxlength="4000"></textarea>
          <button class="btn sm" style="margin-top: 8px" onclick={() => reply(m)} disabled={busy === m.name || !(replies[m.name] || '').trim() || res.cached}>Send reply</button>
        {/if}
      </div>
    {:else}
      <Empty icon="✉️" title={unanswered ? 'All caught up' : 'No messages yet'} />
    {/each}
  {/if}
</div>
