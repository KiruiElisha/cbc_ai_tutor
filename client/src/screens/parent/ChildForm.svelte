<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText, needsPlan } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import TopBar from '../../components/TopBar.svelte'
  import Modal from '../../components/Modal.svelte'

  let { params } = $props()
  const editing = !!params.id

  let grades = $state([])
  let schoolQuery = $state('')
  let schools = $state([])
  let f = $state({ first_name: '', last_name: '', grade: '', school: '', date_of_birth: '', gender: '', relation: '', pin: '' })
  let pin2 = $state('')
  let busy = $state(false)
  let error = $state('')
  let created = $state(null)
  let showCode = $state(false)

  onMount(async () => {
    grades = await get('curriculum.grades', {}, { guest: true }).catch(() => [])
    if (editing) {
      const r = await get('parent.child_progress', { student: params.id })
      const l = r.learner
      const [first, ...rest] = (l.name || '').split(' ')
      f.first_name = l.first_name || first
      f.last_name = rest.join(' ')
      f.grade = l.grade || ''
      f.school = l.school || ''
      schoolQuery = l.school || ''
    }
  })

  let timer
  function searchSchools() {
    clearTimeout(timer)
    timer = setTimeout(async () => {
      schools = schoolQuery.length >= 2 ? await get('curriculum.schools', { txt: schoolQuery }, { guest: true }).catch(() => []) : []
    }, 250)
  }

  async function submit(e) {
    e.preventDefault()
    error = ''
    if (!editing && f.pin !== pin2) {
      error = 'The two PINs do not match.'
      return
    }
    busy = true
    try {
      if (editing) {
        await api('parent.update_child', {
          student: params.id,
          first_name: f.first_name,
          last_name: f.last_name,
          grade: f.grade,
          school: f.school || '',
        })
        toast('Saved.', 'ok')
        go('/child/' + enc(params.id), { replace: true })
      } else {
        created = await api('parent.add_child', { ...f, school: f.school || null, date_of_birth: f.date_of_birth || null })
        showCode = true
      }
    } catch (err) {
      error = needsPlan(err) ? errorText(err) + ' Open Plan to upgrade.' : errorText(err)
    } finally {
      busy = false
    }
  }

  function done() {
    showCode = false
    go('/', { replace: true })
  }
</script>

<TopBar title={editing ? 'Edit child' : 'Add a child'} backTo={editing ? '/child/' + enc(params.id) : '/'} />
<div class="page">
  <form class="card" onsubmit={submit} style="max-width: 560px">
    <div class="row wrap">
      <label class="field grow"><span>First name</span><input bind:value={f.first_name} required /></label>
      <label class="field grow"><span>Last name</span><input bind:value={f.last_name} /></label>
    </div>
    <label class="field">
      <span>Grade</span>
      <select bind:value={f.grade} required>
        <option value="">Choose…</option>
        {#each grades as g}<option value={g.name}>{g.program_name}</option>{/each}
      </select>
    </label>
    <label class="field">
      <span>School (optional, lets teachers set assignments)</span>
      <input bind:value={schoolQuery} oninput={() => { f.school = ''; searchSchools() }} placeholder="Type the school name" />
      {#if f.school}<span class="small" style="color: var(--ok)">✓ {f.school}</span>{/if}
      {#if schools.length && !f.school}
        <div class="card flat" style="padding: 4px; margin-top: 4px">
          {#each schools as s}
            <button type="button" class="nav-link" onclick={() => { f.school = s.name; schoolQuery = s.school_name; schools = [] }}>
              {s.school_name} <span class="muted small">{s.county || ''}</span>
            </button>
          {/each}
        </div>
      {/if}
    </label>
    {#if !editing}
      <div class="row wrap">
        <label class="field grow"><span>Date of birth</span><input type="date" bind:value={f.date_of_birth} /></label>
        <label class="field grow"><span>Gender</span>
          <select bind:value={f.gender}><option value="">Prefer not to say</option><option>Female</option><option>Male</option></select>
        </label>
        <label class="field grow"><span>You are their</span>
          <select bind:value={f.relation}><option value="">Guardian</option><option>Mother</option><option>Father</option><option value="Others">Other</option></select>
        </label>
      </div>
      <div class="row wrap">
        <label class="field grow"><span>Child's PIN (4–8 digits)</span><input class="pin-input" type="password" inputmode="numeric" pattern="[0-9]*" minlength="4" maxlength="8" bind:value={f.pin} required /></label>
        <label class="field grow"><span>PIN again</span><input class="pin-input" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="8" bind:value={pin2} required /></label>
      </div>
      <p class="small muted">Avoid easy PINs like 1234 or 0000. Your child signs in with their learner code and this PIN.</p>
    {/if}
    {#if error}<div class="banner bad">{error}</div>{/if}
    <button class="btn" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save' : 'Add child'}</button>
  </form>
</div>

<Modal bind:open={showCode} title="All set! 🎉">
  {#if created}
    <p>{created.learner.name} can now sign in on any device with:</p>
    <div class="card center" style="background: var(--brand-soft)">
      <div class="small muted">Learner code</div>
      <div style="font-size: 2rem; font-weight: 800; letter-spacing: 0.2em">{created.learner_code}</div>
      <div class="small muted">and the PIN you chose</div>
    </div>
    <p class="small muted" style="margin-top: 10px">Write the code down. You can always see it on the Children screen.</p>
    <button class="btn block" onclick={done}>Done</button>
  {/if}
</Modal>
