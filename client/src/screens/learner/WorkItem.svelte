<script>
  import { onMount } from 'svelte'
  import { app, queue, toast } from '../../lib/app.svelte.js'
  import { errorText, fileToBase64 } from '../../lib/tauri.js'
  import FilePreview from '../../components/FilePreview.svelte'
  import { date, dateTime, markdown, plain } from '../../lib/format.js'
  import * as L from '../../lib/learner.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Empty from '../../components/Empty.svelte'

  let { params } = $props()
  let a = $state(null)
  let sub = $state(null)
  let answer = $state('')
  let file = $state(null)
  let busy = $state(false)
  let loading = $state(true)

  async function load() {
    a = (await L.mine('assignment')).find((x) => x.name === params.id) || null
    sub = (await L.mine('submission')).find((s) => s.assignment === params.id) || null
    if (sub?.answer_text && !answer) answer = plain(sub.answer_text)
    loading = false
  }
  onMount(load)

  let canSubmit = $derived(a && a.status === 'Published' && (!sub || ['Returned', 'Not accepted', 'Submitted', 'Late', 'Waiting to send'].includes(sub.status)))

  async function submit(e) {
    e.preventDefault()
    if (!answer.trim() && !file) return
    if (file && file.size > 8 * 1024 * 1024) {
      toast('Files can be up to 8 MB. Take a smaller photo.', 'error')
      return
    }
    busy = true
    try {
      const payload = { assignment: a.name, answer_text: answer.trim(), submitted_at: new Date().toISOString().slice(0, 19).replace('T', ' ') }
      if (file) {
        payload.attachment_name = file.name
        payload.attachment_data = await fileToBase64(file)
      }
      await queue('assignment_submission', payload)
      toast(app.online ? 'Sending your work…' : 'Saved. It will send when you are online.', 'ok')
      file = null
      await load()
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }
</script>

<TopBar title={a?.title || 'Assignment'} backTo="/work" />
<div class="page">
  {#if loading}
    <Loading />
  {:else if !a}
    <Empty icon="🔍" title="Assignment not found"><p>Sync to refresh your assignments.</p></Empty>
  {:else}
    <div class="row wrap small" style="margin-bottom: 10px">
      <span class="pill brand">{a.assignment_type}</span>
      {#if a.due_date}<span class="pill">Due {date(a.due_date)}</span>{/if}
      {#if a.competency_type}<span class="pill">{a.competency_type}</span>{/if}
      {#if a.status === 'Closed'}<span class="pill bad">Closed</span>{/if}
    </div>
    <h1>{a.title}</h1>
    <div class="card prose">{@html markdown(a.description || '')}</div>
    {#if a.attachment}
      <div style="margin-top: 12px"><FilePreview fileUrl={a.attachment} label={app.online ? 'Open the worksheet' : 'Worksheet (needs internet)'} /></div>
    {/if}

    {#if sub}
      <div class="card" style="margin-top: 14px">
        <div class="row between"><h3 style="margin: 0">Your work</h3><span class="pill">{sub.status}</span></div>
        {#if sub.submission_date}<div class="small muted">Handed in {dateTime(sub.submission_date)}</div>{/if}
        {#if sub.sync_error}<div class="banner bad small" style="margin-top: 8px">{sub.sync_error}</div>{/if}
        {#if sub.grade_given || sub.remarks}
          <div class="banner ok" style="margin-top: 10px">
            <div><b>Teacher's feedback</b>{#if sub.grade_given}: {sub.grade_given}{/if}<br />{sub.remarks || ''}</div>
          </div>
        {/if}
      </div>
    {/if}

    {#if canSubmit}
      <form class="card" style="margin-top: 14px" onsubmit={submit}>
        <h3>{sub ? 'Hand in again' : 'Hand in your work'}</h3>
        <label class="field"><span>Your answer</span><textarea bind:value={answer} maxlength="20000" placeholder="Write your answer here…"></textarea></label>
        <label class="field">
          <span>Photo or file (optional)</span>
          <input type="file" accept="image/*,.pdf,.doc,.docx,.txt,audio/*" capture="environment" onchange={(e) => (file = e.currentTarget.files?.[0] || null)} />
        </label>
        <button class="btn" disabled={busy || (!answer.trim() && !file)}>{busy ? 'Saving…' : 'Hand in'}</button>
        {#if !app.online}<div class="small muted" style="margin-top: 8px">You are offline. Your work is saved and sends when you reconnect.</div>{/if}
      </form>
    {/if}
  {/if}
</div>
