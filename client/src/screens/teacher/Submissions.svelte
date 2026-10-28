<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText } from '../../lib/tauri.js'
  import { enc } from '../../lib/router.svelte.js'
  import { date, dateTime, safeHtml } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Modal from '../../components/Modal.svelte'
  import FilePreview from '../../components/FilePreview.svelte'

  let { params } = $props()
  let data = $state(null)
  let error = $state(null)
  let filter = $state('new')
  let current = $state(null)
  let open = $state(false)
  let grade = $state('')
  let remarks = $state('')
  let busy = $state(false)

  async function load() {
    error = null
    try {
      data = await get('teacher.submissions', { assignment: params.id })
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  const isNew = (r) => r.status === 'Submitted' || r.status === 'Late'
  let rows = $derived(
    (data?.learners || []).filter((r) => (filter === 'new' ? isNew(r) : filter === 'missing' ? !r.submission : filter === 'done' ? r.submission && !isNew(r) : true)),
  )

  function review(r) {
    current = r
    grade = r.grade_given || ''
    remarks = r.remarks || ''
    open = true
  }

  async function save(status) {
    busy = true
    try {
      const row = await api('teacher.review_submission', { name: current.submission, grade_given: grade, remarks, status })
      const i = data.learners.findIndex((x) => x.student === row.student)
      if (i >= 0) data.learners[i] = row
      open = false
      toast(status === 'Returned' ? 'Sent back to redo.' : 'Marked.', 'ok')
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      busy = false
    }
  }

  const tone = (s) => ({ Reviewed: 'ok', Submitted: 'brand', Late: 'warn', Returned: 'warn', 'Not submitted': 'bad' })[s] || ''
  const count = (k) => (data?.learners || []).filter((r) => (k === 'new' ? isNew(r) : k === 'missing' ? !r.submission : k === 'done' ? r.submission && !isNew(r) : true)).length
</script>

<TopBar title={data?.title || 'Submissions'} backTo={'/assignment/' + enc(params.id)} />
<div class="page">
  <ErrorBox {error} retry={load} />
  {#if !data && !error}
    <Loading />
  {:else if data}
    {#if data.due_date}<p class="muted" style="margin-top: 0">Due {date(data.due_date)}</p>{/if}
    <div class="tabs">
      {#each [['new', 'To review'], ['done', 'Marked'], ['missing', 'Not handed in'], ['all', 'Everyone']] as [k, label]}
        <button class="tab" class:on={filter === k} onclick={() => (filter = k)}>{label} ({count(k)})</button>
      {/each}
    </div>
    {#each rows as r}
      <div class="card flat row">
        <div class="grow">
          <b>{r.student_name}</b>
          <div class="small muted">{r.submitted_on ? 'Handed in ' + dateTime(r.submitted_on) : 'Nothing yet'}{r.grade_given ? ' · ' + r.grade_given : ''}</div>
        </div>
        <span class="pill {tone(r.status)}">{r.status}</span>
        {#if r.submission}<button class="btn sm" onclick={() => review(r)}>{isNew(r) ? 'Review' : 'Open'}</button>{/if}
      </div>
    {:else}
      <p class="muted">Nobody here.</p>
    {/each}
  {/if}
</div>

<Modal bind:open title={current?.student_name || ''}>
  {#if current}
    <div class="small muted">Handed in {dateTime(current.submitted_on)} · {current.status}</div>
    {#if current.answer_text}
      <div class="card flat prose" style="margin: 10px 0">{@html safeHtml(current.answer_text)}</div>
    {/if}
    {#if current.attachment}
      <FilePreview fileUrl={current.attachment} path="teacher.file" label="Open their file" />
    {/if}
    <label class="field" style="margin-top: 12px"><span>Mark or level</span><input bind:value={grade} maxlength="140" placeholder="e.g. 8/10 or Proficient" /></label>
    <label class="field"><span>Feedback for the learner</span><textarea bind:value={remarks} maxlength="2000"></textarea></label>
    <div class="row">
      <button class="btn grow" onclick={() => save('Reviewed')} disabled={busy}>Mark as reviewed</button>
      <button class="btn ghost" onclick={() => save('Returned')} disabled={busy || !remarks.trim()} title="Needs feedback">Send back to redo</button>
    </div>
  {/if}
</Modal>
