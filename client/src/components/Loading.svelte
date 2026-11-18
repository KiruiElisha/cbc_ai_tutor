<script>
  // Shapes of the content on its way instead of a spinner: the page feels quicker on a slow line.
  let { rows = 3 } = $props()
</script>

<div class="skeleton" aria-busy="true" aria-label="Loading">
  {#each Array(rows) as _, i}
    <div class="sk-card">
      <div class="sk-line" style="width: {[62, 48, 70][i % 3]}%"></div>
      <div class="sk-line short"></div>
      <div class="sk-line" style="width: {[84, 76, 90][i % 3]}%"></div>
    </div>
  {/each}
</div>

<style>
  .skeleton { display: grid; gap: 12px; padding: 4px 0; }
  .sk-card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 16px; display: grid; gap: 10px; }
  .sk-line { height: 12px; border-radius: 99px; width: 80%; background: linear-gradient(90deg, var(--line) 25%, var(--bg) 50%, var(--line) 75%); background-size: 200% 100%; animation: shimmer 1.2s infinite linear; }
  .sk-line.short { width: 35%; }
  @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
</style>
