<script>
  import Modal from './Modal.svelte'
  import { checkPin, setPin } from '../lib/parentPin.js'

  /**
   * mode 'set': the parent picks a PIN before handing the device over (or skips).
   * mode 'check': the PIN is needed to go back to the parent's view.
   * `onpass()` runs once the PIN is set, skipped or correct.
   */
  let { open = $bindable(false), mode = 'check', onpass } = $props()
  let pin = $state('')
  let again = $state('')
  let wrong = $state('')

  async function submit(e) {
    e.preventDefault()
    wrong = ''
    if (mode === 'set') {
      if (pin !== again) return (wrong = 'The two PINs are different.')
      await setPin(pin)
    } else if (!(await checkPin(pin))) {
      pin = ''
      return (wrong = 'That PIN is not right.')
    }
    finish()
  }

  function finish() {
    open = false
    pin = again = ''
    onpass?.()
  }
</script>

<Modal bind:open title={mode === 'set' ? 'Set a parent PIN' : 'Parent PIN'}>
  <form onsubmit={submit}>
    <p class="muted" style="margin-top: 0">
      {mode === 'set'
        ? 'Your child needs this PIN to leave their lessons and see your account, payments or other children. Pick 4 digits only you know.'
        : 'Enter the parent PIN to go back to the parent view.'}
    </p>
    <label class="field"><span>PIN</span>
      <input class="pin-input" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="off" bind:value={pin} required />
    </label>
    {#if mode === 'set'}
      <label class="field"><span>The same PIN again</span>
        <input class="pin-input" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="off" bind:value={again} required />
      </label>
    {/if}
    {#if wrong}<p style="color: var(--bad)">{wrong}</p>{/if}
    <button class="btn block">{mode === 'set' ? 'Set PIN and continue' : 'Back to parent'}</button>
    {#if mode === 'set'}
      <button type="button" class="link" style="margin-top: 12px" onclick={finish}>Skip for now</button>
    {:else}
      <p class="small muted" style="margin-bottom: 0">Forgot it? Sign out from More, then sign in again as the parent: the PIN is cleared.</p>
    {/if}
  </form>
</Modal>
