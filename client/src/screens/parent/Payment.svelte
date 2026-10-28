<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText, isOffline } from '../../lib/tauri.js'
  import { go } from '../../lib/router.svelte.js'
  import { date, money } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'

  let { params } = $props()
  let tx = $state(null)
  let error = $state('')
  let busy = $state(false)
  let tries = 0
  let timer

  async function poll() {
    try {
      tx = await get('billing.transaction', { name: params.tx })
      error = ''
    } catch (e) {
      error = isOffline(e) ? 'No internet. Still waiting…' : errorText(e)
    }
    tries++
    if ((!tx || tx.status === 'Pending') && tries < 120) timer = setTimeout(poll, tries < 20 ? 4000 : 10000)
  }

  onMount(() => {
    poll()
    return () => clearTimeout(timer)
  })

  async function cancel() {
    busy = true
    try {
      const r = await api('billing.cancel_pending', { name: params.tx })
      clearTimeout(timer)
      tx = { ...tx, status: r.status }
      if (r.status === 'Completed') await poll()
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      busy = false
    }
  }
</script>

<TopBar title="Payment" backTo="/plans" />
<div class="page">
  <div class="card center" style="max-width: 480px; margin: 20px auto">
    {#if !tx || tx.status === 'Pending'}
      <div style="font-size: 3rem">⏳</div>
      <h2>Waiting for payment</h2>
      {#if tx?.gateway === 'PayPal'}
        <p>Finish paying in the PayPal page that opened. This screen updates by itself.</p>
      {:else}
        <p>Check your phone and enter your M-Pesa PIN. This screen updates by itself.</p>
      {/if}
      {#if tx}<p class="small muted">{money(tx.amount, tx.currency)}</p>{/if}
      <div class="loading"><span class="spinner"></span></div>
      <button class="btn ghost" onclick={cancel} disabled={busy || !tx}>I didn't pay, cancel</button>
    {:else if tx.status === 'Completed'}
      <div style="font-size: 3rem">✅</div>
      <h2>Payment received</h2>
      <p>{money(tx.amount, tx.currency)}{tx.receipt_number ? ` · receipt ${tx.receipt_number}` : ''}</p>
      {#if tx.subscription}<p>Your plan is active until <b>{date(tx.subscription.until)}</b>.</p>{/if}
      <button class="btn" onclick={() => go('/', { replace: true })}>Back to my children</button>
    {:else}
      <div style="font-size: 3rem">{tx.status === 'Cancelled' ? '🚫' : '❌'}</div>
      <h2>{tx.status === 'Cancelled' ? 'Payment cancelled' : 'Payment did not go through'}</h2>
      {#if tx.failure_reason}<p class="muted">{tx.failure_reason}</p>{/if}
      <p class="small muted">No money was taken for this attempt. If M-Pesa shows a deduction, it is matched automatically within a few minutes.</p>
      <button class="btn" onclick={() => go('/plans', { replace: true })}>Try again</button>
    {/if}
    {#if error}<div class="banner warn small" style="margin-top: 12px">{error}</div>{/if}
  </div>
</div>
