<script>
  import { back } from '../lib/router.svelte.js'

  let { title = '', backTo = null, children } = $props()
</script>

<header class="topbar">
  {#if backTo !== null}
    <button class="icon-btn" aria-label="Back" onclick={() => back(backTo)}>←</button>
  {/if}
  <div class="title">{title}</div>
  {@render children?.()}
</header>
