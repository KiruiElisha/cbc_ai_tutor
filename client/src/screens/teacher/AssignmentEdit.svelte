<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText, fileToBase64 } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { markdown } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import Modal from '../../components/Modal.svelte'
  import CurriculumPicker from '../../components/CurriculumPicker.svelte'
  import FilePreview from '../../components/FilePreview.svelte'

  let { params } = $props()
  const id = params.id || null

  let grades = $state([])
  let f = $state({
    title: '', assignment_type: 'Assignment', description: '', due_date: '', grade: '', area: '', strand: '',
    sub_strand: '', learning_outcome: '', performance_indicator: '', competency_type: '', attachment: '',
  })
  let status = $state('Draft')
  let loading = $state(!!id)
  let busy = $state(false)
  let uploading = $state(false)
  let preview = $state(false)
  let aiOpen = $state(false)
  let aiNotes = $state('')
  let drafting = $state(false)

  onMount(async () => {
    grades = await get('curriculum.grades', {}, { guest: true }).catch(() => [])
    if (id) {
      try {
        const a = await get('teacher.assignment', { name: id })
        for (const k of Object.keys(f)) if (a[k] != null) f[k] = a[k]
        status = a.status
      } catch (e) {
        toast(errorText(e), 'error')
      }
      loading = false
    }
  })

  async function upload(e) {
    const file = e.currentTarget.files?.[0]
    if (!file) return
    if (file.size > 8 * 1024 * 1024) return toast('Files can be up to 8 MB.', 'error')
    uploading = true
    try {
      const r = await api('teacher.upload', { filename: file.name, content: await fileToBase64(file) })
      f.attachment = r.file_url
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      uploading = false
    }
  }

  function payload() {
    const { area, ...rest } = f
    return { ...rest, name: id, due_date: f.due_date || null }
  }

  async function save(e, publish = false) {
    e?.preventDefault()
    busy = true
    try {
      let a = await api('teacher.save_assignment', payload())
      if (publish) a = await api('teacher.set_assignment_status', { name: a.name, status: 'Published' })
      toast(publish ? 'Published. Learners get it on their next sync.' : 'Saved.', 'ok')
      go('/assignments', { replace: true })
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function setStatus(s) {
    busy = true
    try {
      const a = await api('teacher.set_assignment_status', { name: id, status: s })
      status = a.status
      toast(`Now ${s.toLowerCase()}.`, 'ok')
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function remove() {
    if (!confirm('Delete this assignment?')) return
    busy = true
    try {
      await api('teacher.delete_assignment', { name: id })
      go('/assignments', { replace: true })
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function draft(e) {
    e.preventDefault()
    drafting = true
    try {
      const d = await api('tutor.draft_assignment', {
        grade: f.grade,
        learning_area: f.area || null,
        sub_strand: f.sub_strand || null,
        learning_outcome: f.learning_outcome || null,
        kind: f.assignment_type,
        notes: aiNotes || null,
      })
      if (d.title) f.title = d.title
      if (d.description) f.description = d.description
      aiOpen = false
      toast('Draft ready. Check and edit it before publishing.', 'ok')
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      drafting = false
    }
  }

  let locked = $derived(status === 'Closed')
</script>

<TopBar title={id ? 'Edit assignment' : 'New assignment'} backTo="/assignments">
  {#if id && status !== 'Draft'}<a class="btn sm ghost" href={'#/assignment/' + enc(id) + '/submissions'}>Submissions</a>{/if}
</TopBar>
<div class="page">
  {#if loading}
    <Loading />
  {:else}
    {#if id}
      <div class="row wrap" style="margin-bottom: 10px">
        <span class="pill {status === 'Published' ? 'ok' : status === 'Closed' ? 'bad' : ''}">{status}</span>
        {#if status === 'Published'}<button class="btn sm ghost" onclick={() => setStatus('Closed')} disabled={busy}>Close</button>{/if}
        {#if status === 'Closed'}<button class="btn sm ghost" onclick={() => setStatus('Published')} disabled={busy}>Reopen</button>{/if}
        {#if status === 'Draft'}<button class="btn sm ghost danger" onclick={remove} disabled={busy}>Delete</button>{/if}
      </div>
    {/if}
    <form class="card" onsubmit={(e) => save(e)} style="max-width: 760px">
      <div class="row wrap">
        <label class="field grow">
          <span>Grade</span>
          <select bind:value={f.grade} required disabled={locked} onchange={() => (f.area = f.strand = f.sub_strand = f.learning_outcome = f.performance_indicator = '')}>
            <option value="">Choose…</option>
            {#each grades as g}<option value={g.name}>{g.program_name}</option>{/each}
          </select>
        </label>
        <label class="field grow">
          <span>Kind</span>
          <select bind:value={f.assignment_type} disabled={locked}>{#each ['Assignment', 'Homework', 'Project', 'Quiz'] as t}<option>{t}</option>{/each}</select>
        </label>
        <label class="field grow"><span>Due date</span><input type="date" bind:value={f.due_date} disabled={locked} /></label>
      </div>

      {#if f.grade}
        {#key f.grade}
          <CurriculumPicker grade={f.grade} bind:area={f.area} bind:strand={f.strand} bind:sub_strand={f.sub_strand} bind:learning_outcome={f.learning_outcome} bind:performance_indicator={f.performance_indicator} />
        {/key}
        <label class="field">
          <span>Competency focus (optional)</span>
          <select bind:value={f.competency_type} disabled={locked}>
            <option value="">None</option>
            {#each ['Knowledge', 'Skills', 'Values & Attitudes'] as c}<option>{c}</option>{/each}
          </select>
        </label>
      {/if}

      <label class="field"><span>Title</span><input bind:value={f.title} maxlength="140" required disabled={locked} /></label>
      <label class="field">
        <span class="row between">
          Instructions
          <span class="row">
            <button type="button" class="btn sm ghost" onclick={() => (preview = !preview)}>{preview ? 'Edit' : 'Preview'}</button>
            <button type="button" class="btn sm soft" onclick={() => (aiOpen = true)} disabled={!f.grade || locked}>✨ Draft with AI</button>
          </span>
        </span>
        {#if preview}
          <div class="card flat prose">{@html markdown(f.description || '*Nothing yet*')}</div>
        {:else}
          <textarea bind:value={f.description} rows="10" disabled={locked} placeholder="What should learners do? You can use **bold**, lists and headings."></textarea>
        {/if}
      </label>

      <div class="field">
        <span>Worksheet (optional)</span>
        <div class="row wrap">
          {#if f.attachment}
            <FilePreview fileUrl={f.attachment} path="teacher.file" label={f.attachment.split('/').pop()} />
            <button type="button" class="btn sm ghost" onclick={() => (f.attachment = '')} disabled={locked}>Remove</button>
          {/if}
          <input type="file" accept="image/*,.pdf,.doc,.docx,.txt" onchange={upload} disabled={uploading || locked} />
          {#if uploading}<span class="small muted">Uploading…</span>{/if}
        </div>
      </div>

      {#if !locked}
        <div class="row wrap">
          <button class="btn ghost" disabled={busy || uploading}>Save{status === 'Draft' ? ' draft' : ''}</button>
          {#if status === 'Draft'}
            <button type="button" class="btn" onclick={() => save(null, true)} disabled={busy || uploading || !f.title || !f.grade}>Save and publish</button>
          {/if}
        </div>
      {/if}
    </form>
  {/if}
</div>

<Modal bind:open={aiOpen} title="Draft with AI">
  <form onsubmit={draft}>
    <p class="small muted">The AI writes a first draft for {f.grade}{f.learning_outcome ? ' on the chosen learning outcome' : f.sub_strand ? ' on the chosen sub-strand' : ''}. It replaces the title and instructions; check them before publishing.</p>
    <label class="field"><span>Anything to include? (optional)</span><textarea bind:value={aiNotes} maxlength="1000" placeholder="e.g. use items found at home, 3 questions, group work"></textarea></label>
    <button class="btn block" disabled={drafting}>{drafting ? 'Writing…' : 'Write a draft'}</button>
  </form>
</Modal>
