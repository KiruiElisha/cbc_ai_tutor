<script>
  import { onMount } from 'svelte'
  import { app, syncNow } from '../../lib/app.svelte.js'
  import { call } from '../../lib/tauri.js'
  import { ago, dateTime } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'

  let items = $state([])
  const labels = {
    lesson_progress: 'Lesson progress',
    quiz_attempt: 'Quiz answers',
    assignment_submission: 'Assignment',
    practice_answers: 'Practice answers',
    ai_feedback: 'Tutor feedback',
  }

  async function load() {
    items = await call('outbox_list')
  }

  async function run() {
    await syncNow()
    await load()
  }

  async function discard(uuid) {
    await call('outbox_discard', { uuid })
    await load()
  }

  onMount(load)
</script>

<TopBar title="Sync" backTo="/" />
<div class="page">
  <div class="card">
    <div class="row between wrap">
      <div>
        <b>{app.online ? 'Online' : 'Offline'}</b>
        <div class="small muted">Last synced {ago(app.lastSync)}</div>
      </div>
      <button class="btn" onclick={run} disabled={app.syncing}>{app.syncing ? 'Syncing…' : 'Sync now'}</button>
    </div>
    {#if app.syncError}<div class="banner bad small" style="margin-top: 10px">{app.syncError}</div>{/if}
    <p class="small muted" style="margin: 10px 0 0">The app syncs by itself every few minutes when there is internet. Everything you do offline is kept until it is sent.</p>
  </div>

  <div class="section"><h2>Waiting to send</h2><span class="pill">{items.filter((i) => i.state === 'pending').length}</span></div>
  {#each items as i}
    <div class="card flat row">
      <div class="grow">
        <b>{labels[i.type] || i.type}</b>
        <div class="small muted">{dateTime(i.at)}{i.attempts ? ` · tried ${i.attempts}×` : ''}</div>
        {#if i.error}<div class="small" style="color: var(--bad)">{i.error}</div>{/if}
      </div>
      {#if i.state === 'rejected'}
        <span class="pill bad">Not accepted</span>
        <button class="btn sm ghost" onclick={() => discard(i.uuid)}>Remove</button>
      {:else}
        <span class="pill warn">Waiting</span>
      {/if}
    </div>
  {:else}
    <p class="muted">Everything is sent. ✅</p>
  {/each}
</div>
