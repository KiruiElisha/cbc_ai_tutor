<script>
  import { refreshState } from '../../lib/app.svelte.js'
  import { call, errorText } from '../../lib/tauri.js'
  import { go } from '../../lib/router.svelte.js'

  let code = $state('')
  let pin = $state('')
  let busy = $state(false)
  let error = $state('')

  async function submit(e) {
    e.preventDefault()
    busy = true
    error = ''
    try {
      await call('learner_login', { code: code.replace(/[\s-]/g, '').toUpperCase(), pin })
      await refreshState()
      go('/', { replace: true })
    } catch (err) {
      error = errorText(err)
      pin = ''
    } finally {
      busy = false
    }
  }
</script>

<div class="auth-wrap">
  <form class="auth card" onsubmit={submit}>
    <button type="button" class="link small" onclick={() => go('/')}>← Back</button>
    <div class="center" style="font-size: 3rem">🎒</div>
    <h1 class="center">Hello, learner!</h1>
    <p class="muted center small">Your parent can see your learner code in their app.</p>
    <label class="field">
      <span>Learner code</span>
      <input class="code-input" bind:value={code} maxlength="8" autocapitalize="characters" autocomplete="off" spellcheck="false" required />
    </label>
    <label class="field">
      <span>PIN</span>
      <input class="pin-input" type="password" inputmode="numeric" pattern="[0-9]*" bind:value={pin} maxlength="8" autocomplete="off" required />
    </label>
    {#if error}<div class="banner bad">{error}</div>{/if}
    <button class="btn block" disabled={busy || code.length < 6 || pin.length < 4}>{busy ? 'Opening…' : "Let's learn"}</button>
  </form>
</div>
