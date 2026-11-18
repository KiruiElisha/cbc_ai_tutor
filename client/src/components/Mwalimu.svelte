<script>
  /**
   * Mwalimu, drawn: an owl in a kikoi scarf of the flag's colours. One small inline SVG, so it costs
   * nothing to load. `mood`: 'calm' (default), 'think' (eyes up, while an answer is written) or
   * 'happy' (smiling eyes, after a right answer).
   */
  let { size = 40, mood = 'calm' } = $props()
</script>

<svg class="mwalimu mood-{mood}" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Mwalimu">
  <circle cx="32" cy="32" r="31" fill="#fff" />
  <!-- body and ear tufts -->
  <path d="M14 26c0-11 8-18 18-18s18 7 18 18v14c0 10-8 18-18 18s-18-8-18-18z" fill="#8a5a3b" />
  <path d="M15 14l7 6-8 2zM49 14l-7 6 8 2z" fill="#6b4329" />
  <ellipse cx="32" cy="44" rx="11" ry="10" fill="#e9d2b4" />
  <!-- eyes -->
  <circle cx="24" cy="27" r="8" fill="#fff" />
  <circle cx="40" cy="27" r="8" fill="#fff" />
  {#if mood === 'happy'}
    <path d="M19 28q5-5 10 0M35 28q5-5 10 0" stroke="#141414" stroke-width="2.6" fill="none" stroke-linecap="round" />
  {:else}
    <circle class="pupil" cx="24" cy={mood === 'think' ? 24 : 28} r="3.6" fill="#141414" />
    <circle class="pupil" cx="40" cy={mood === 'think' ? 24 : 28} r="3.6" fill="#141414" />
  {/if}
  <!-- glasses, as a teacher's -->
  <circle cx="24" cy="27" r="8.6" fill="none" stroke="#141414" stroke-width="1.6" />
  <circle cx="40" cy="27" r="8.6" fill="none" stroke="#141414" stroke-width="1.6" />
  <path d="M32.6 27h-1.2" stroke="#141414" stroke-width="1.6" />
  <path d="M30 33l2 4 2-4z" fill="#f59e0b" />
  <!-- kikoi scarf: black, red, green with white edges -->
  <path d="M17 49q15 7 30 0v4q-15 7-30 0z" fill="#141414" />
  <path d="M17 52q15 7 30 0v3q-15 7-30 0z" fill="#b8211a" />
  <path d="M17 54.5q15 7 30 0v2.5q-15 7-30 0z" fill="#0b7a3d" />
  <circle cx="32" cy="32" r="31" fill="none" stroke="#b8211a" stroke-width="2" />
</svg>

<style>
  .mwalimu { display: block; flex-shrink: 0; border-radius: 50%; }
  .mood-think .pupil { animation: look 2.4s ease-in-out infinite; }
  @keyframes look { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(1.5px); } }
</style>
