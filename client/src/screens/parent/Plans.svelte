<script>
  import { onMount } from 'svelte'
  import { openUrl } from '@tauri-apps/plugin-opener'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText } from '../../lib/tauri.js'
  import { go, enc } from '../../lib/router.svelte.js'
  import { date, dateTime, kes, money } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Modal from '../../components/Modal.svelte'

  let catalog = $state(null)
  let sub = $state(null)
  let error = $state(null)
  let chosen = $state(null)
  let payOpen = $state(false)
  let phone = $state(localStorage.getItem('cbc:mpesa_phone') || '')
  let busy = $state(false)

  async function load() {
    error = null
    try {
      ;[catalog, sub] = await Promise.all([get('billing.plans'), get('billing.subscription')])
    } catch (e) {
      error = e
    }
  }
  onMount(load)

  function choose(p) {
    chosen = p
    payOpen = true
  }

  async function mpesa(e) {
    e.preventDefault()
    busy = true
    try {
      const r = await api('billing.pay_mpesa', { plan: chosen.name, phone })
      localStorage.setItem('cbc:mpesa_phone', phone)
      payOpen = false
      toast(r.message, 'info')
      go('/payment/' + enc(r.transaction))
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function paypal() {
    busy = true
    try {
      const r = await api('billing.pay_paypal', { plan: chosen.name })
      payOpen = false
      await openUrl(r.approve_url)
      go('/payment/' + enc(r.transaction))
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  const statusTone = (s) => ({ Completed: 'ok', Failed: 'bad', Cancelled: '' })[s] || 'warn'

  // The plan that costs least per day, shown with its daily price so the saving is clear.
  const perDay = (p) => Math.round((p.price_kes / (p.duration_days || 1)) * 10) / 10
  let bestValue = $derived(
    catalog?.plans?.length ? catalog.plans.reduce((a, b) => (perDay(b) < perDay(a) ? b : a)).name : null,
  )
</script>

<TopBar title="Plan and payments" />
<div class="page">
  <ErrorBox {error} retry={load} />
  {#if !catalog && !error}
    <Loading />
  {:else if catalog && sub}
    <div class="card" style="background: {sub.active ? 'var(--brand-soft)' : ''}">
      <div class="small muted">Your plan</div>
      <h2 style="margin: 4px 0">{sub.plan || (sub.status === 'Trial' ? 'Free trial' : 'No plan')}</h2>
      <div class="small">
        {#if sub.active}Active until <b>{date(sub.until)}</b>{:else}<span style="color: var(--bad)">Not active</span>{/if}
        · {sub.learners} of {sub.max_learners} learners
        · {sub.ai_messages_per_day ? sub.ai_messages_per_day + ' Mwalimu messages a day each' : 'unlimited Mwalimu'}
      </div>
      <p class="small muted" style="margin: 8px 0 0">Paying adds the plan's days on top of any time you still have.</p>
    </div>

    {#each sub.pending as p}
      <a class="banner info" href={'#/payment/' + enc(p.name)} style="text-decoration: none">⏳ <span class="grow">A {p.gateway} payment of {money(p.amount, p.currency)} is waiting. <b>Check it</b></span></a>
    {/each}

    <div class="section"><h2>Choose a plan</h2></div>
    {#if !catalog.gateways.mpesa && !catalog.gateways.paypal}
      <div class="banner warn">Payments are not set up yet.</div>
    {/if}
    <div class="grid">
      {#each catalog.plans as p}
        <div class="card stack" class:best={p.name === bestValue}>
          <div>
            {#if p.name === bestValue && catalog.plans.length > 1}<span class="ribbon">BEST VALUE · KES {perDay(p)} a day</span>{/if}
            <h3 style="margin: 0">{p.plan_name}</h3>
            {#if p.tagline}<div class="small muted">{p.tagline}</div>{/if}
          </div>
          <div><span class="stat">{kes(p.price_kes)}</span> <span class="small muted">/ {p.duration_days} days</span></div>
          {#if p.price_paypal}<div class="small muted">or {money(p.price_paypal, p.paypal_currency)} with PayPal</div>{/if}
          <ul class="small" style="padding-left: 18px; margin: 0">
            {#if p.features.length}
              {#each p.features as f}<li>{f}</li>{/each}
            {:else}
              <li>Up to {p.max_learners} learners</li>
              <li>{p.ai_messages_per_day ? p.ai_messages_per_day + ' Mwalimu messages a day each' : 'Unlimited Mwalimu'}</li>
            {/if}
          </ul>
          <button class="btn" onclick={() => choose(p)} disabled={!catalog.gateways.mpesa && !catalog.gateways.paypal}>
            {sub.plan === p.plan_name && sub.active ? 'Renew' : 'Choose'}
          </button>
        </div>
      {/each}
    </div>

    {#if sub.history.length}
      <div class="section"><h2>Payment history</h2></div>
      {#each sub.history as h}
        <div class="card flat row">
          <div class="grow">
            <b>{h.plan}</b> · {money(h.amount, h.currency)}
            <div class="small muted">{h.gateway} · {dateTime(h.completed_on || h.creation)}{h.receipt_number ? ' · ' + h.receipt_number : ''}</div>
            {#if h.status === 'Failed' && h.failure_reason}<div class="small muted">{h.failure_reason}</div>{/if}
          </div>
          <span class="pill {statusTone(h.status)}">{h.status}</span>
        </div>
      {/each}
    {/if}
  {/if}
</div>

<Modal bind:open={payOpen} title={chosen ? `Pay for ${chosen.plan_name}` : 'Pay'}>
  {#if chosen}
    {#if catalog.gateways.mpesa}
      <form onsubmit={mpesa}>
        <h3 style="margin-top: 0">M-Pesa · {kes(chosen.price_kes)}</h3>
        <label class="field">
          <span>Safaricom number</span>
          <input type="tel" inputmode="tel" placeholder="07XX XXX XXX" bind:value={phone} required autocomplete="tel" />
        </label>
        <button class="btn block" disabled={busy || phone.replace(/\D/g, '').length < 9}>{busy ? 'Sending prompt…' : 'Send M-Pesa prompt'}</button>
        <p class="small muted">A prompt appears on the phone. Enter your M-Pesa PIN to pay.</p>
      </form>
    {/if}
    {#if catalog.gateways.paypal && chosen.price_paypal}
      {#if catalog.gateways.mpesa}<hr style="border: 0; border-top: 1px solid var(--line); margin: 16px 0" />{/if}
      <h3 style="margin-top: 0">PayPal or card · {money(chosen.price_paypal, chosen.paypal_currency)}</h3>
      <button class="btn block ghost" onclick={paypal} disabled={busy}>Continue to PayPal</button>
      <p class="small muted">PayPal opens in your browser. Come back to the app when you're done.</p>
    {/if}
  {/if}
</Modal>
