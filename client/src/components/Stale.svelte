<script>
  import { ago } from '../lib/format.js'

  let { result = null } = $props()
</script>

{#if result?.cached}
  <div class="banner info small">📶 Offline. Showing what was saved {ago(result.saved)}.</div>
{/if}
