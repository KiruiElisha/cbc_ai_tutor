<script>
  import Mwalimu from './Mwalimu.svelte'
  import { t } from '../lib/i18n.js'
  // Mwalimu one tap away while a learner reads or answers: stuck is when help matters most.
  let { href, label = t('Stuck? Ask Mwalimu') } = $props()
</script>

<a class="ask-fab" {href}><span class="fab-face"><Mwalimu size={36} /></span><span class="fab-label">{label}</span></a>
