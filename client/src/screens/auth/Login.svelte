<script>
  import { refreshState, toast } from '../../lib/app.svelte.js'
  import { api, call, errorText } from '../../lib/tauri.js'
  import { go } from '../../lib/router.svelte.js'

  let { params } = $props()
  const role = params.role === 'teacher' ? 'Teacher' : 'Parent'

  let login = $state('')
  let password = $state('')
  let busy = $state(false)
  let error = $state('')
  let resetOpen = $state(false)

  async function submit(e) {
    e.preventDefault()
    busy = true
    error = ''
    try {
      await call('login', { login, password, role })
      await refreshState()
      go('/', { replace: true })
    } catch (err) {
      error = errorText(err)
    } finally {
      busy = false
    }
  }

  async function reset() {
    if (!login.includes('@')) {
      error = 'Type your email address above first.'
      return
    }
    busy = true
    try {
      const res = await api('auth.request_password_reset', { email: login }, { guest: true })
      toast(res.message, 'ok')
      resetOpen = false
    } catch (err) {
      error = errorText(err)
    } finally {
      busy = false
    }
  }
</script>

<div class="auth-wrap">
  <form class="auth card" onsubmit={submit}>
    <button type="button" class="link small" onclick={() => go('/')}>← Back</button>
    <h1 style="margin-top: 10px">{role === 'Teacher' ? 'Teacher sign in' : 'Parent sign in'}</h1>
    <label class="field">
      <span>Email or phone number</span>
      <input bind:value={login} autocomplete="username" autocapitalize="off" required />
    </label>
    <label class="field">
      <span>Password</span>
      <input type="password" bind:value={password} autocomplete="current-password" required />
    </label>
    {#if error}<div class="banner bad">{error}</div>{/if}
    <button class="btn block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    <div class="row between small" style="margin-top: 14px">
      <button type="button" class="link" onclick={() => (resetOpen = !resetOpen)}>Forgot password?</button>
      {#if role === 'Parent'}<a href="#/signup">Create an account</a>{/if}
    </div>
    {#if resetOpen}
      <div class="banner info" style="margin-top: 12px">
        <div class="grow small">We will email a link to reset your password.</div>
        <button type="button" class="btn sm" onclick={reset} disabled={busy}>Send link</button>
      </div>
    {/if}
    {#if role === 'Teacher'}
      <p class="small muted" style="margin-top: 14px">Teacher accounts are created by the school. Ask your administrator if you don't have one.</p>
    {/if}
  </form>
</div>
