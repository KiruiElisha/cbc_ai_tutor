<script>
  import { app, refreshState, toast } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go } from '../../lib/router.svelte.js'

  let url = $state(app.server || 'https://')
  let busy = $state(false)
  let error = $state('')

  async function save(e) {
    e.preventDefault()
    busy = true
    error = ''
    try {
      await call('set_server', { url })
      await refreshState()
      toast('Connected to the server.', 'ok')
      go('/', { replace: true })
    } catch (err) {
      error = errorText(err)
    } finally {
      busy = false
    }
  }
</script>

<div class="auth-wrap">
  <form class="auth card" onsubmit={save}>
    <img class="logo" src="/logo.svg" alt="" />
    <h1 class="center">Connect to your school's server</h1>
    <p class="muted center">Enter the address you were given, for example https://tutor.myschool.co.ke</p>
    <label class="field">
      <span>Server address</span>
      <input bind:value={url} inputmode="url" autocapitalize="off" autocomplete="url" spellcheck="false" required />
    </label>
    {#if error}<div class="banner bad">{error}</div>{/if}
    <button class="btn block" disabled={busy}>{busy ? 'Checking…' : 'Connect'}</button>
  </form>
</div>
