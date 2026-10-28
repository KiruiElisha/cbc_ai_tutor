<script>
  let { icon = '📭', title = '', children } = $props()
</script>

<div class="empty">
  <div class="big">{icon}</div>
  {#if title}<h3>{title}</h3>{/if}
  {@render children?.()}
</div>
