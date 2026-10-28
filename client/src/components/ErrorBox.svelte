<script>
  import { errorText } from '../lib/tauri.js'
  import { go } from '../lib/router.svelte.js'

  let { error = null, retry = null } = $props()
</script>

{#if error}
  <div class="banner {error.kind === 'offline' ? 'info' : 'bad'}">
    <span>{error.kind === 'offline' ? '📶' : '⚠️'}</span>
    <div class="grow">
      {errorText(error)}
      {#if error.kind === 'subscription_required'}
        <div class="small">Ask a parent to renew the family plan.</div>
      {/if}
    </div>
    {#if retry}<button class="btn sm ghost" onclick={retry}>Try again</button>{/if}
    {#if error.kind === 'signed_out'}<button class="btn sm" onclick={() => go('/')}>Sign in</button>{/if}
  </div>
{/if}
