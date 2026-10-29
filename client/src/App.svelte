<script module>
  import { route } from './lib/router.svelte.js'

  route('/', 'home')
  route('/login/:role', 'login')
  route('/signup', 'signup')
  route('/learner-login', 'learner_login')
  route('/settings', 'settings')
  // learner
  route('/area/:course', 'area')
  route('/lesson/:id', 'lesson')
  route('/quiz/:id', 'quiz')
  route('/tutor', 'tutor')
  route('/practice', 'practice')
  route('/work', 'work')
  route('/work/:id', 'work_item')
  route('/progress', 'my_progress')
  route('/sync', 'sync')
  // parent
  route('/child/new', 'child_new')
  route('/child/:id', 'child')
  route('/child/:id/edit', 'child_edit')
  route('/plans', 'plans')
  route('/payment/:tx', 'payment')
  route('/messages', 'messages')
  // teacher
  route('/students', 'students')
  route('/student/:id', 'student')
  route('/assignments', 'assignments')
  route('/assignment/new', 'assignment_new')
  route('/assignment/:id', 'assignment_edit')
  route('/assignment/:id/submissions', 'submissions')
  route('/inbox', 'inbox')
</script>

<script>
  import { onMount } from 'svelte'
  import { onOpenUrl, getCurrent } from '@tauri-apps/plugin-deep-link'
  import { app, toasts, refreshState, syncNow, startAutoSync, stopAutoSync, toast } from './lib/app.svelte.js'
  import { call, errorText } from './lib/tauri.js'
  import { router, go } from './lib/router.svelte.js'
  import Loading from './components/Loading.svelte'

  import Welcome from './screens/auth/Welcome.svelte'
  import Login from './screens/auth/Login.svelte'
  import Signup from './screens/auth/Signup.svelte'
  import LearnerLogin from './screens/auth/LearnerLogin.svelte'
  import Settings from './screens/Settings.svelte'

  import LearnerHome from './screens/learner/Home.svelte'
  import Area from './screens/learner/Area.svelte'
  import Lesson from './screens/learner/Lesson.svelte'
  import Quiz from './screens/learner/Quiz.svelte'
  import Tutor from './screens/learner/Tutor.svelte'
  import Practice from './screens/learner/Practice.svelte'
  import Work from './screens/learner/Work.svelte'
  import WorkItem from './screens/learner/WorkItem.svelte'
  import MyProgress from './screens/learner/MyProgress.svelte'
  import Sync from './screens/learner/Sync.svelte'

  import ParentHome from './screens/parent/Home.svelte'
  import ChildForm from './screens/parent/ChildForm.svelte'
  import Child from './screens/parent/Child.svelte'
  import Plans from './screens/parent/Plans.svelte'
  import Payment from './screens/parent/Payment.svelte'
  import Messages from './screens/parent/Messages.svelte'

  import TeacherHome from './screens/teacher/Home.svelte'
  import Students from './screens/teacher/Students.svelte'
  import Student from './screens/teacher/Student.svelte'
  import Assignments from './screens/teacher/Assignments.svelte'
  import AssignmentEdit from './screens/teacher/AssignmentEdit.svelte'
  import Submissions from './screens/teacher/Submissions.svelte'
  import Inbox from './screens/teacher/Inbox.svelte'

  const screens = {
    guest: { home: Welcome, login: Login, signup: Signup, learner_login: LearnerLogin, settings: Settings },
    Learner: {
      home: LearnerHome, area: Area, lesson: Lesson, quiz: Quiz, tutor: Tutor, practice: Practice,
      work: Work, work_item: WorkItem, my_progress: MyProgress, sync: Sync, settings: Settings,
    },
    Parent: {
      home: ParentHome, child_new: ChildForm, child_edit: ChildForm, child: Child, plans: Plans,
      payment: Payment, messages: Messages, settings: Settings,
    },
    Teacher: {
      home: TeacherHome, students: Students, student: Student, assignments: Assignments,
      assignment_new: AssignmentEdit, assignment_edit: AssignmentEdit, submissions: Submissions,
      inbox: Inbox, settings: Settings,
    },
  }

  const navs = {
    Learner: [
      ['/', '🏠', 'Learn'],
      ['/tutor', '💬', 'Mwalimu'],
      ['/work', '📝', 'Assignments'],
      ['/progress', '⭐', 'Progress'],
      ['/settings', '⚙️', 'More'],
    ],
    Parent: [
      ['/', '👨‍👩‍👧', 'Children'],
      ['/plans', '💳', 'Plan'],
      ['/messages', '✉️', 'Messages'],
      ['/settings', '⚙️', 'More'],
    ],
    Teacher: [
      ['/', '🏫', 'Home'],
      ['/students', '👧', 'Learners'],
      ['/assignments', '📝', 'Assignments'],
      ['/inbox', '✉️', 'Parents'],
      ['/settings', '⚙️', 'More'],
    ],
  }

  let roleKey = $derived(app.session?.role || 'guest')
  let Screen = $derived.by(() => screens[roleKey]?.[router.name] || screens[roleKey]?.home || Welcome)
  let nav = $derived(navs[roleKey] || null)
  let current = $derived('/' + (router.path.split('?')[0].split('/')[1] || ''))

  const seenLinks = new Set()
  let boot = Promise.resolve()

  async function handleLinks(urls) {
    await boot
    for (const raw of urls || []) {
      let u
      try {
        u = new URL(raw)
      } catch {
        continue
      }
      const tx = u.searchParams.get('tx')
      if ((u.host === 'payment' || u.pathname.includes('payment')) && tx) go('/payment/' + encodeURIComponent(tx))
      const code = u.searchParams.get('code')
      if (u.protocol !== 'cbctutor:' || u.host !== 'auth' || !code || seenLinks.has(code)) continue
      seenLinks.add(code)
      try {
        await call('finish_signin', { code })
        await refreshState()
        go('/', { replace: true })
      } catch (err) {
        seenLinks.delete(code)
        toast(errorText(err), 'error')
      }
    }
  }

  let lastRole = null
  $effect(() => {
    const r = app.session?.role || null
    if (r === lastRole) return
    lastRole = r
    if (r === 'Learner') {
      syncNow({ quiet: true })
      startAutoSync()
    } else {
      stopAutoSync()
    }
  })

  onMount(() => {
    boot = refreshState().catch(() => (app.ready = true))
    let unlisten
    onOpenUrl(handleLinks).then((u) => (unlisten = u)).catch(() => {})
    getCurrent().then(handleLinks).catch(() => {})
    return () => unlisten?.()
  })
</script>

{#if !app.ready}
  <Loading />
{:else if !nav}
  {#key router.path}<Screen params={router.params} />{/key}
{:else}
  <div class="shell">
    <aside class="side">
      <div class="brand"><img src="/logo.svg" alt="" /> CBC Tutor</div>
      {#each nav as [path, icon, label]}
        <a class="nav-link" class:on={current === path} href={'#' + path}><span class="ico">{icon}</span>{label}</a>
      {/each}
      <div class="grow"></div>
      <div class="small muted" style="padding: 0 12px">
        {app.session?.profile?.learner?.name || app.session?.profile?.full_name || ''}
        {#if roleKey === 'Learner' && app.pending}<br />{app.pending} waiting to send{/if}
      </div>
    </aside>
    <div class="main">
      {#key router.path}<Screen params={router.params} />{/key}
    </div>
    <nav class="bottom">
      {#each nav as [path, icon, label]}
        <a class="nav-link grow" class:on={current === path} href={'#' + path}><span class="ico">{icon}</span>{label}</a>
      {/each}
    </nav>
  </div>
{/if}

<div class="toasts" aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast {t.tone}">{t.message}</div>
  {/each}
</div>
