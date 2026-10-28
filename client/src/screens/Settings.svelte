<script>
  import { onMount } from 'svelte'
  import { app, refreshState, toast } from '../lib/app.svelte.js'
  import { api, get, call, errorText } from '../lib/tauri.js'
  import { go } from '../lib/router.svelte.js'
  import { ago } from '../lib/format.js'
  import TopBar from '../components/TopBar.svelte'
  import Modal from '../components/Modal.svelte'

  let role = $derived(app.session?.role || null)
  let adult = $derived(role === 'Parent' || role === 'Teacher')
  let devices = $state(null)
  let pwOpen = $state(false)
  let pw = $state({ old: '', next: '', again: '' })
  let busy = $state(false)

  async function loadDevices() {
    try {
      devices = await get('auth.devices')
    } catch {
      devices = null
    }
  }
  onMount(() => {
    if (adult) loadDevices()
  })

  async function signOutDevice(d) {
    try {
      await api('auth.sign_out_device', { name: d.name })
      await loadDevices()
    } catch (e) {
      toast(errorText(e), 'error')
    }
  }

  async function changePassword(e) {
    e.preventDefault()
    if (pw.next !== pw.again) return toast('The new passwords do not match.', 'error')
    busy = true
    try {
      const r = await api('auth.change_password', { old_password: pw.old, new_password: pw.next })
      pwOpen = false
      pw = { old: '', next: '', again: '' }
      toast(r.message, 'ok')
      loadDevices()
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function backToParent() {
    try {
      await call('back_to_parent')
      await refreshState()
      go('/', { replace: true })
    } catch (e) {
      toast(errorText(e), 'error')
    }
  }

  async function logout() {
    if (role === 'Learner' && app.pending && !confirm(`${app.pending} item(s) have not been sent yet and will be lost. Sign out anyway?`)) return
    busy = true
    try {
      await call('logout')
    } catch {}
    await refreshState()
    busy = false
    go('/', { replace: true })
  }

  async function wipe() {
    if (!confirm('Remove all accounts, lessons and unsent work from this device?')) return
    await call('wipe_device')
    await refreshState()
    go('/', { replace: true })
  }
</script>

<TopBar title="Settings" backTo={role ? null : '/'} />
<div class="page" style="max-width: 720px">
  {#if app.session}
    <div class="card">
      <div class="small muted">Signed in as</div>
      <b>{app.session.profile?.learner?.name || app.session.profile?.full_name || app.session.user}</b>
      <div class="small muted">{role}{app.session.profile?.learner?.learner_code ? ' · ' + app.session.profile.learner.learner_code : ''}</div>
      <div class="row wrap" style="margin-top: 12px">
        {#if role === 'Learner' && app.parentWaiting}
          <button class="btn sm" onclick={backToParent}>Back to parent</button>
        {/if}
        {#if role === 'Learner'}<a class="btn sm ghost" href="#/sync">Sync ({app.pending} waiting)</a>{/if}
        {#if adult}<button class="btn sm ghost" onclick={() => (pwOpen = true)}>Change password</button>{/if}
        <button class="btn sm ghost danger" onclick={logout} disabled={busy}>Sign out</button>
      </div>
    </div>
  {/if}

  {#if adult && devices}
    <div class="section"><h2>Signed-in devices</h2></div>
    {#each devices as d}
      <div class="card flat row">
        <div class="grow">
          <b>{d.device_name || d.platform || 'Device'}</b>{#if d.current} <span class="pill ok">This device</span>{/if}
          <div class="small muted">{d.role_type}{d.student ? ' (child)' : ''} · last seen {ago(d.last_seen)}</div>
        </div>
        {#if !d.current}<button class="btn sm ghost" onclick={() => signOutDevice(d)}>Sign out</button>{/if}
      </div>
    {/each}
  {/if}

  <div class="section"><h2>This device</h2></div>
  <div class="card flat">
    <div class="row between"><span>Server</span><span class="small muted">{app.server || 'Not set'}</span></div>
    {#if !app.session}<a class="btn sm ghost" style="margin-top: 8px" href="#/server">Change server</a>{/if}
  </div>
  <div class="card flat">
    <div class="row between"><span>App version</span><span class="small muted">{app.version} · {app.platform}</span></div>
  </div>
  <div class="card flat">
    <div class="row between wrap">
      <div><b>Remove everything from this device</b><div class="small muted">For shared or sold devices.</div></div>
      <button class="btn sm ghost danger" onclick={wipe}>Remove</button>
    </div>
  </div>
</div>

<Modal bind:open={pwOpen} title="Change password">
  <form onsubmit={changePassword}>
    <label class="field"><span>Current password</span><input type="password" bind:value={pw.old} autocomplete="current-password" required /></label>
    <label class="field"><span>New password (8+ characters)</span><input type="password" bind:value={pw.next} minlength="8" autocomplete="new-password" required /></label>
    <label class="field"><span>New password again</span><input type="password" bind:value={pw.again} autocomplete="new-password" required /></label>
    <p class="small muted">Other devices are signed out.</p>
    <button class="btn block" disabled={busy}>Change password</button>
  </form>
</Modal>
