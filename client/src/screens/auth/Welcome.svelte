<script>
  import { go } from '../../lib/router.svelte.js'
</script>

<div class="auth-wrap">
  <div class="auth">
    <img class="logo" src="/logo.svg" alt="" />
    <h1 class="center">Karibu CBC Tutor</h1>
    <p class="muted center">Lessons, quizzes and Mwalimu the AI tutor, for every CBC grade. Works offline.</p>
    <div class="stack" style="margin-top: 22px">
      <button class="card tap role-btn" onclick={() => go('/learner-login')}>
        <span class="emoji">🎒</span>
        <span class="grow"><b>I am a learner</b><br /><span class="muted small">Sign in with your learner code and PIN</span></span>
      </button>
      <button class="card tap role-btn" onclick={() => go('/login/parent')}>
        <span class="emoji">👨‍👩‍👧</span>
        <span class="grow"><b>I am a parent</b><br /><span class="muted small">Add your children, follow progress, manage the plan</span></span>
      </button>
      <button class="card tap role-btn" onclick={() => go('/login/teacher')}>
        <span class="emoji">🧑🏾‍🏫</span>
        <span class="grow"><b>I am a teacher</b><br /><span class="muted small">Set assignments and record CBC assessments</span></span>
      </button>
    </div>
    <p class="center small" style="margin-top: 18px">
      New parent? <a href="#/signup">Create a free account</a>
    </p>
  </div>
</div>
