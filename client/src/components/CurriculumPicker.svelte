<script>
  import { get, errorText } from '../lib/tauri.js'
  import { plain } from '../lib/format.js'

  let {
    grade,
    area = $bindable(''),
    strand = $bindable(''),
    sub_strand = $bindable(''),
    learning_outcome = $bindable(''),
    performance_indicator = $bindable(''),
    requireOutcome = false,
    showIndicator = true,
  } = $props()

  let tree = $state(null)
  let error = $state('')
  let loadedFor = ''

  $effect(() => {
    if (!grade || grade === loadedFor) return
    loadedFor = grade
    tree = null
    error = ''
    get('curriculum.tree', { grade }, { cache: 'tree:' + grade })
      .then((r) => {
        tree = r.data
        if (strand && !area) area = tree.strands.find((s) => s.name === strand)?.course || ''
      })
      .catch((e) => (error = errorText(e)))
  })

  const byOrder = (a, b) => (a.order || 0) - (b.order || 0) || String(a.title || a.name).localeCompare(String(b.title || b.name))
  let strands = $derived(tree ? tree.strands.filter((s) => s.course === area && s.active !== 0).sort(byOrder) : [])
  let subs = $derived(tree ? tree.sub_strands.filter((s) => s.strand === strand && s.active !== 0).sort(byOrder) : [])
  let outs = $derived(tree ? tree.outcomes.filter((o) => o.sub_strand === sub_strand).sort(byOrder) : [])
  let indicators = $derived(outs.find((o) => o.name === learning_outcome)?.indicators || [])

  const clip = (t, n = 90) => {
    const s = plain(t || '')
    return s.length > n ? s.slice(0, n - 1) + '…' : s
  }
</script>

{#if error}
  <div class="banner bad small">{error}</div>
{:else if !tree}
  <div class="small muted">Loading the curriculum…</div>
{:else}
  <label class="field">
    <span>Learning area</span>
    <select bind:value={area} onchange={() => (strand = sub_strand = learning_outcome = performance_indicator = '')} required={requireOutcome}>
      <option value="">{requireOutcome ? 'Choose…' : 'Any'}</option>
      {#each tree.learning_areas as a}<option value={a.name}>{a.title}</option>{/each}
    </select>
  </label>
  {#if area}
    <label class="field">
      <span>Strand</span>
      <select bind:value={strand} onchange={() => (sub_strand = learning_outcome = performance_indicator = '')} required={requireOutcome}>
        <option value="">{strands.length ? 'Choose…' : 'No strands yet'}</option>
        {#each strands as s}<option value={s.name}>{s.title}</option>{/each}
      </select>
    </label>
  {/if}
  {#if strand}
    <label class="field">
      <span>Sub-strand</span>
      <select bind:value={sub_strand} onchange={() => (learning_outcome = performance_indicator = '')} required={requireOutcome}>
        <option value="">{subs.length ? 'Choose…' : 'No sub-strands yet'}</option>
        {#each subs as s}<option value={s.name}>{s.title}</option>{/each}
      </select>
    </label>
  {/if}
  {#if sub_strand}
    <label class="field">
      <span>Learning outcome</span>
      <select bind:value={learning_outcome} onchange={() => (performance_indicator = '')} required={requireOutcome}>
        <option value="">{outs.length ? 'Choose…' : 'No outcomes yet'}</option>
        {#each outs as o}<option value={o.name}>{clip(o.description)}</option>{/each}
      </select>
    </label>
  {/if}
  {#if showIndicator && indicators.length}
    <label class="field">
      <span>Performance indicator (optional)</span>
      <select bind:value={performance_indicator}>
        <option value="">None</option>
        {#each indicators as p}<option value={p.name}>{clip(p.description)}</option>{/each}
      </select>
    </label>
  {/if}
{/if}
