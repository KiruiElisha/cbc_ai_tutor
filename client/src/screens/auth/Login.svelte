<script>
  import { onMount } from 'svelte'
  import { openUrl } from '@tauri-apps/plugin-opener'
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

  let google = $state(false)
  let codeOpen = $state(false)
  let email = $state('')
  let code = $state('')
  let codeSent = $state(false)
  let needsProfile = $state(false)
  let fullName = $state('')
  let phone = $state('')

  onMount(async () => {
    try {
      const options = await api('signin.options', {}, { method: 'GET', guest: true })
      google = !!options?.google
    } catch {
      google = false
    }
  })

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

  async function sendCode(e) {
    e?.preventDefault()
    busy = true
    error = ''
    try {
      const res = await call('request_email_code', { email, role })
      codeSent = true
      toast(res.message || 'Check your email for the code.', 'ok')
    } catch (err) {
      error = errorText(err)
    } finally {
      busy = false
    }
  }

  async function confirmCode(e) {
    e.preventDefault()
    busy = true
    error = ''
    try {
      const res = await call('confirm_email_code', {
        email,
        code,
        role,
        fullName: needsProfile ? fullName : null,
        phone: needsProfile ? phone : null,
      })
      if (res?.needs_profile) {
        needsProfile = true
        return
      }
      await refreshState()
      go('/', { replace: true })
    } catch (err) {
      error = errorText(err)
    } finally {
      busy = false
    }
  }

  async function googleSignIn() {
    busy = true
    error = ''
    try {
      const res = await call('google_signin_url', { role })
      await openUrl(res.url)
      toast('Finish in the browser, then come back to the app.', 'info')
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
    {#if error && !codeOpen}<div class="banner bad">{error}</div>{/if}
    <button class="btn block" disabled={busy}>{busy && !codeOpen ? 'Signing in…' : 'Sign in'}</button>
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
  </form>

  <div class="auth" style="margin-top: 14px">
    <p class="center small muted" style="margin: 4px 0 12px">or sign in without a password</p>
    {#if google}
      <button type="button" class="btn ghost block" disabled={busy} onclick={googleSignIn}>Continue with Google</button>
    {/if}
    {#if !codeOpen}
      <button type="button" class="btn ghost block" style="margin-top: 10px" disabled={busy} onclick={() => (codeOpen = true)}>
        Email me a code
      </button>
    {:else}
      <form class="card" style="margin-top: 10px" onsubmit={codeSent ? confirmCode : sendCode}>
        <label class="field">
          <span>Email address</span>
          <input type="email" bind:value={email} autocomplete="email" autocapitalize="off" required disabled={codeSent} />
        </label>
        {#if codeSent}
          <label class="field">
            <span>6-digit code</span>
            <input class="pin-input" bind:value={code} inputmode="numeric" autocomplete="one-time-code" maxlength="6" required />
          </label>
        {/if}
        {#if needsProfile}
          <p class="small">This email is new. Add your name and the M-Pesa number you will pay with.</p>
          <label class="field">
            <span>Your name</span>
            <input bind:value={fullName} autocomplete="name" required />
          </label>
          <label class="field">
            <span>M-Pesa phone number</span>
            <input bind:value={phone} inputmode="tel" autocomplete="tel" placeholder="0712 345 678" required />
          </label>
        {/if}
        {#if error}<div class="banner bad">{error}</div>{/if}
        <button class="btn block" disabled={busy}>
          {busy ? 'Please wait…' : codeSent ? 'Continue' : 'Send code'}
        </button>
        {#if codeSent}
          <button type="button" class="link small" style="margin-top: 10px" disabled={busy} onclick={sendCode}>Send a new code</button>
        {/if}
      </form>
    {/if}
    {#if role === 'Teacher'}
      <p class="small muted" style="margin-top: 14px">Teacher accounts are created by the school. Ask your administrator if you don't have one.</p>
    {/if}
  </div>
</div>
