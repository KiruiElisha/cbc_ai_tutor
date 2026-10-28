<script>
  import { onMount } from 'svelte'
  import { toast } from '../../lib/app.svelte.js'
  import { api, get, errorText } from '../../lib/tauri.js'
  import { ago, date, dateTime, level, initials, nowString } from '../../lib/format.js'
  import TopBar from '../../components/TopBar.svelte'
  import Loading from '../../components/Loading.svelte'
  import ErrorBox from '../../components/ErrorBox.svelte'
  import Stale from '../../components/Stale.svelte'
  import Modal from '../../components/Modal.svelte'
  import CurriculumPicker from '../../components/CurriculumPicker.svelte'

  let { params } = $props()
  const id = params.id
  const today = () => nowString().slice(0, 10)

  let res = $state(null)
  let error = $state(null)
  let busy = $state(false)

  let compOpen = $state(false)
  let comp = $state({ area: '', strand: '', sub_strand: '', learning_outcome: '', performance_indicator: '', status: 'Proficient', comments: '', date: today() })
  let assessOpen = $state(false)
  let assess = $state({ area: '', strand: '', sub_strand: '', learning_outcome: '', performance_indicator: '', assessment_type: 'Test', score: '', max_score: 100, comments: '', date: today() })

  async function load() {
    error = null
    try {
      res = await get('teacher.student_progress', { student: id }, { cache: 'teacher:student:' + id })
    } catch (e) {
      error = e
    }
  }
  onMount(load)
  let r = $derived(res?.data)

  async function saveCompetency(e) {
    e.preventDefault()
    busy = true
    try {
      await api('teacher.record_competency', {
        student: id,
        learning_outcome: comp.learning_outcome,
        performance_indicator: comp.performance_indicator || null,
        status: comp.status,
        comments: comp.comments || null,
        date: comp.date,
      })
      compOpen = false
      comp.comments = ''
      toast('Observation saved. The parent can see it.', 'ok')
      await load()
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  async function saveAssessment(e) {
    e.preventDefault()
    busy = true
    try {
      await api('teacher.record_assessment', {
        student: id,
        subject: assess.area,
        assessment_type: assess.assessment_type,
        score: Number(assess.score),
        max_score: Number(assess.max_score),
        comments: assess.comments || null,
        strand: assess.strand || null,
        sub_strand: assess.sub_strand || null,
        learning_outcome: assess.learning_outcome || null,
        date: assess.date,
      })
      assessOpen = false
      assess.score = ''
      assess.comments = ''
      toast('Assessment saved.', 'ok')
      await load()
    } catch (err) {
      toast(errorText(err), 'error')
    } finally {
      busy = false
    }
  }

  const tone = (s) => ({ Advanced: 'ok', Proficient: 'brand', Emerging: 'warn', Reviewed: 'ok', Returned: 'warn', 'Not submitted': 'bad' })[s] || ''
</script>

<TopBar title={r?.learner.name || 'Learner'} backTo="/students" />
<div class="page">
  <Stale result={res} />
  <ErrorBox {error} retry={load} />
  {#if !res && !error}
    <Loading />
  {:else if r}
    <div class="card">
      <div class="row">
        <div class="avatar lg">{initials(r.learner.name)}</div>
        <div class="grow">
          <h2 style="margin: 0">{r.learner.name}</h2>
          <div class="small muted">{r.learner.grade} · {r.learner.learner_code} · active {ago(r.summary.last_active)}</div>
        </div>
      </div>
      <div class="row wrap" style="margin-top: 12px">
        <button class="btn sm" onclick={() => (compOpen = true)} disabled={res.cached}>Record observation</button>
        <button class="btn sm ghost" onclick={() => (assessOpen = true)} disabled={res.cached}>Record assessment</button>
      </div>
    </div>

    <div class="section"><h2>Learning areas</h2></div>
    {#each r.learning_areas.filter((a) => a.lessons) as a}
      <div class="card flat">
        <div class="row between"><b>{a.title}</b><span class="small muted">{a.completed}/{a.lessons}</span></div>
        <div class="bar" style="margin: 8px 0"><i style="width: {a.percent}%"></i></div>
        <div class="small muted">{a.quiz_average != null ? `Quizzes ${Math.round(a.quiz_average)}% · ${level(a.quiz_average)}` : 'No quizzes yet'}{a.minutes ? ` · ${a.minutes} min` : ''}</div>
      </div>
    {:else}
      <p class="muted">No lessons done yet.</p>
    {/each}

    <div class="section"><h2>Observations</h2></div>
    {#each r.competencies as c}
      <div class="card flat">
        <div class="row between"><span class="pill {tone(c.status)}">{c.status}</span><span class="small muted">{date(c.date)}</span></div>
        <p style="margin: 8px 0 4px">{c.outcome || c.learning_outcome}</p>
        {#if c.comments}<div class="small muted">“{c.comments}”</div>{/if}
      </div>
    {:else}
      <p class="muted small">None yet.</p>
    {/each}

    <div class="section"><h2>Assessments</h2></div>
    {#each r.assessments as s}
      <div class="card flat row">
        <div class="grow"><b>{s.subject}</b><div class="small muted">{s.assessment_type} · {date(s.date)}</div>{#if s.comments}<div class="small">{s.comments}</div>{/if}</div>
        <b>{s.score}/{s.max_score}</b>
      </div>
    {:else}
      <p class="muted small">None yet.</p>
    {/each}

    <div class="section"><h2>Recent quizzes</h2></div>
    {#each r.recent_quizzes as q}
      <div class="card flat row">
        <div class="grow"><b>{q.lesson_title || q.quiz}</b><div class="small muted">{dateTime(q.time_completed || q.creation)}</div></div>
        <span class="pill {q.score >= 50 ? 'ok' : 'warn'}">{Math.round(q.score)}%</span>
      </div>
    {:else}
      <p class="muted small">None yet.</p>
    {/each}

    <div class="section"><h2>Assignments</h2></div>
    {#each r.assignments as w}
      <div class="card flat row">
        <div class="grow"><b>{w.title}</b><div class="small muted">{w.type}{w.due_date ? ' · due ' + date(w.due_date) : ''}</div></div>
        <span class="pill {tone(w.status)}">{w.grade_given || w.status}</span>
      </div>
    {:else}
      <p class="muted small">None yet.</p>
    {/each}
  {/if}
</div>

{#if r}
  <Modal bind:open={compOpen} title="Record an observation">
    <form onsubmit={saveCompetency}>
      <CurriculumPicker grade={r.learner.grade} requireOutcome bind:area={comp.area} bind:strand={comp.strand} bind:sub_strand={comp.sub_strand} bind:learning_outcome={comp.learning_outcome} bind:performance_indicator={comp.performance_indicator} />
      <label class="field">
        <span>Level</span>
        <div class="row wrap">
          {#each ['Emerging', 'Proficient', 'Advanced'] as lv}
            <button type="button" class="btn sm" class:ghost={comp.status !== lv} onclick={() => (comp.status = lv)}>{lv}</button>
          {/each}
        </div>
      </label>
      <label class="field"><span>Comments</span><textarea bind:value={comp.comments} maxlength="1000"></textarea></label>
      <label class="field"><span>Date</span><input type="date" bind:value={comp.date} max={today()} /></label>
      <button class="btn block" disabled={busy || !comp.learning_outcome}>Save</button>
    </form>
  </Modal>

  <Modal bind:open={assessOpen} title="Record an assessment">
    <form onsubmit={saveAssessment}>
      <CurriculumPicker grade={r.learner.grade} showIndicator={false} bind:area={assess.area} bind:strand={assess.strand} bind:sub_strand={assess.sub_strand} bind:learning_outcome={assess.learning_outcome} bind:performance_indicator={assess.performance_indicator} />
      <label class="field">
        <span>Kind</span>
        <select bind:value={assess.assessment_type}>{#each ['Test', 'Quiz', 'Project', 'Observation', 'Assignment'] as t}<option>{t}</option>{/each}</select>
      </label>
      <div class="row">
        <label class="field grow"><span>Score</span><input type="number" min="0" step="0.5" bind:value={assess.score} required /></label>
        <label class="field grow"><span>Out of</span><input type="number" min="1" step="0.5" bind:value={assess.max_score} required /></label>
      </div>
      <label class="field"><span>Comments</span><textarea bind:value={assess.comments} maxlength="2000"></textarea></label>
      <label class="field"><span>Date</span><input type="date" bind:value={assess.date} max={today()} /></label>
      <button class="btn block" disabled={busy || !assess.area || assess.score === ''}>Save</button>
    </form>
  </Modal>
{/if}
