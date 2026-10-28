<script>
  import { refreshState, toast } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go } from '../../lib/router.svelte.js'

  let form = $state({ full_name: '', email: '', phone: '', password: '' })
  let confirm = $state('')
  let agree = $state(false)
  let busy = $state(false)
  let error = $state('')

  async function submit(e) {
    e.preventDefault()
    error = ''
    if (form.password !== confirm) {
      error = 'The two passwords do not match.'
      return
    }
    busy = true
    try {
      await call('signup_parent', form)
      await refreshState()
      toast('Welcome! Your free trial has started.', 'ok')
      go('/child/new', { replace: true })
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
    <h1 style="margin-top: 10px">Create a parent account</h1>
    <p class="muted small">Start with a free trial. Add your children next.</p>
    <label class="field"><span>Your full name</span><input bind:value={form.full_name} autocomplete="name" required /></label>
    <label class="field"><span>Email</span><input type="email" bind:value={form.email} autocomplete="email" autocapitalize="off" required /></label>
    <label class="field"><span>M-Pesa phone number</span><input type="tel" bind:value={form.phone} placeholder="0712 345 678" autocomplete="tel" required /></label>
    <label class="field"><span>Password (at least 8 characters)</span><input type="password" bind:value={form.password} autocomplete="new-password" minlength="8" required /></label>
    <label class="field"><span>Password again</span><input type="password" bind:value={confirm} autocomplete="new-password" required /></label>
    <label class="row small" style="margin-bottom: 14px">
      <input type="checkbox" bind:checked={agree} style="width: auto; min-height: 0" required />
      <span>I am the child's parent or guardian and agree to the terms and privacy policy.</span>
    </label>
    {#if error}<div class="banner bad">{error}</div>{/if}
    <button class="btn block" disabled={busy || !agree}>{busy ? 'Creating…' : 'Create account'}</button>
  </form>
</div>
