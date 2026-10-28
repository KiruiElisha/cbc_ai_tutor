<script>
  let { open = $bindable(false), title = '', children } = $props()

  function onkey(e) {
    if (e.key === 'Escape') open = false
  }
</script>

<svelte:window onkeydown={onkey} />

{#if open}
  <div class="modal-bg" role="presentation" onclick={(e) => e.target === e.currentTarget && (open = false)}>
    <div class="modal" role="dialog" aria-modal="true" aria-label={title}>
      <div class="row between" style="margin-bottom: 10px">
        <h2 style="margin: 0">{title}</h2>
        <button class="icon-btn" aria-label="Close" onclick={() => (open = false)}>✕</button>
      </div>
      {@render children?.()}
    </div>
  </div>
{/if}
