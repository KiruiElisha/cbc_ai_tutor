<script>
  // Mwalimu one tap away while a learner reads or answers: stuck is when help matters most.
  let { href, label = 'Stuck? Ask Mwalimu' } = $props()
</script>

<a class="ask-fab" {href}><span class="fab-face" aria-hidden="true">🦉</span><span class="fab-label">{label}</span></a>
