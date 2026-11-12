<script>
  // Every sign-in screen: centred on phones (safe areas, the keyboard and short landscape
  // screens included), and beside a welcome panel on tablets and computers.
  let { children } = $props()
</script>

<div class="auth-wrap">
  <aside class="auth-side" aria-hidden="true">
    <img src={import.meta.env.BASE_URL + 'logo.svg'} alt="" />
    <h2>CBC Tutor</h2>
    <p>Lessons, quizzes and Mwalimu the AI tutor for every CBC grade, Grade 1 to 9.</p>
    <ul>
      <li>📚 Lessons in every learning area</li>
      <li>📝 Quizzes that mark themselves</li>
      <li>📶 Keeps working offline</li>
      <li>👨‍👩‍👧 Parents follow progress</li>
    </ul>
  </aside>
  <div class="auth-main">
    {@render children()}
  </div>
</div>
