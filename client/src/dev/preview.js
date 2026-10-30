/**
 * Browser preview of the app with sample data, for design work and screenshots:
 *   npm run preview:ui        then open http://localhost:1420/?role=Learner (or Parent, Teacher, guest)
 * It stands in for the Rust side (window.__TAURI_INTERNALS__). Never part of a real build.
 */

const role = new URLSearchParams(location.search).get('role') || 'Learner'

const learner = { student: 'EDU-STU-0001', name: 'Amina Wanjiru', first_name: 'Amina', grade: 'Grade 4', learner_code: 'AMW-4821' }

const sessions = {
  Learner: { role: 'Learner', profile: { learner } },
  Parent: { role: 'Parent', profile: { full_name: 'Grace Wanjiru', email: 'grace@example.co.ke' } },
  Teacher: { role: 'Teacher', profile: { full_name: 'Mr. Otieno', school: 'Kilimani Primary' } },
  guest: null,
}

const areas = [
  ['MATH-G4', 'Mathematics'], ['ENG-G4', 'English'], ['KIS-G4', 'Kiswahili'],
  ['SCI-G4', 'Science and Technology'], ['SST-G4', 'Social Studies'], ['AGR-G4', 'Agriculture and Nutrition'],
  ['CRE-G4', 'Creative Arts'], ['RE-G4', 'Religious Education'],
].map(([name, title], order) => ({ name, title, course_name: title, order, description: '' }))

const strands = [
  { name: 'STR-NUM', title: 'Numbers', course: 'MATH-G4', order: 1 },
  { name: 'STR-MEA', title: 'Measurement', course: 'MATH-G4', order: 2 },
  { name: 'STR-LIV', title: 'Living Things and Their Environment', course: 'SCI-G4', order: 1 },
]
const subStrands = [
  { name: 'SUB-WHOLE', title: 'Whole Numbers', strand: 'STR-NUM', order: 1 },
  { name: 'SUB-FRAC', title: 'Fractions', strand: 'STR-NUM', order: 2 },
  { name: 'SUB-LEN', title: 'Length', strand: 'STR-MEA', order: 1 },
  { name: 'SUB-PLANT', title: 'Plants', strand: 'STR-LIV', order: 1 },
]

const body = `<p>A <b>fraction</b> is a part of a whole. When Mama cuts a chapati into 4 equal pieces, each piece is <b>one quarter</b>, written <b>1/4</b>.</p>
<h3>Parts of a fraction</h3><ul><li>The <b>numerator</b> (top number) tells how many parts we have.</li><li>The <b>denominator</b> (bottom number) tells how many equal parts the whole was cut into.</li></ul>
<p>If you eat 3 of the 4 pieces, you have eaten <b>3/4</b> of the chapati.</p>`

const lessons = [
  { name: 'L-WHOLE-1', title: 'Place value up to 100,000', course: 'MATH-G4', strand: 'STR-NUM', sub_strand: 'SUB-WHOLE', estimated_minutes: 20, is_free: 1, locked: 0, quiz: 'Q-PV', summary: 'Read and write big numbers using place value.', body },
  { name: 'L-FRAC-1', title: 'What is a fraction?', course: 'MATH-G4', strand: 'STR-NUM', sub_strand: 'SUB-FRAC', estimated_minutes: 15, is_free: 1, locked: 0, quiz: 'Q-FRAC', summary: 'Fractions are equal parts of a whole, like pieces of a chapati.', body, key_vocabulary: 'fraction, numerator, denominator, equal parts', activities: '<p>Fold a piece of paper into 4 equal parts. Shade 1 part. What fraction is shaded?</p>', reflection: 'Where at home do you share things into equal parts?' },
  { name: 'L-FRAC-2', title: 'Comparing fractions', course: 'MATH-G4', strand: 'STR-NUM', sub_strand: 'SUB-FRAC', estimated_minutes: 20, is_free: 0, locked: 0, summary: 'Which is bigger: 1/2 or 1/4?', body },
  { name: 'L-LEN-1', title: 'Measuring in metres and centimetres', course: 'MATH-G4', strand: 'STR-MEA', sub_strand: 'SUB-LEN', estimated_minutes: 25, is_free: 0, locked: 1, summary: 'Use a metre rule to measure your classroom.', body },
  { name: 'L-PLANT-1', title: 'Parts of a plant', course: 'SCI-G4', strand: 'STR-LIV', sub_strand: 'SUB-PLANT', estimated_minutes: 20, is_free: 1, locked: 0, summary: 'Roots, stem, leaves and flowers each have a job.', body },
]

const questions = [
  { name: 'QQ-1', question: 'A chapati is cut into 4 equal pieces. You eat 1. What fraction did you eat?', options: [{ id: 'a', text: '1/4', is_correct: 1 }, { id: 'b', text: '1/2', is_correct: 0 }, { id: 'c', text: '4/1', is_correct: 0 }, { id: 'd', text: '3/4', is_correct: 0 }] },
  { name: 'QQ-2', question: 'In 3/5, which number is the denominator?', options: [{ id: 'a', text: '3', is_correct: 0 }, { id: 'b', text: '5', is_correct: 1 }, { id: 'c', text: '8', is_correct: 0 }, { id: 'd', text: '2', is_correct: 0 }] },
  { name: 'QQ-3', question: 'Which fraction is bigger?', options: [{ id: 'a', text: '1/2', is_correct: 1 }, { id: 'b', text: '1/4', is_correct: 0 }] },
]
const quizzes = { 'Q-FRAC': { name: 'Q-FRAC', title: 'Fractions check', passing_score: 60, questions: questions.map((q) => q.name), question_rows: questions } }

const content = { area: areas, strand: strands, sub_strand: subStrands, lesson: lessons, outcome: [], quiz: Object.values(quizzes), question: questions }
const parentField = { strand: 'course', sub_strand: 'strand', lesson: 'course', outcome: 'sub_strand' }

const mine = {
  lesson_progress: [{ lesson: 'L-FRAC-1', status: 'In Progress', progress: 60, last_opened: '2026-10-30 08:12:00' }, { lesson: 'L-WHOLE-1', status: 'Completed', progress: 100, last_opened: '2026-10-29 17:40:00' }],
  quiz_attempt: [{ quiz: 'Q-PV', score: 80, created: '2026-10-29 17:45:00' }],
  assignment: [{ name: 'ASG-1', title: 'Measure things at home', status: 'Published', due_date: '2026-11-04', course: 'MATH-G4', description: '<p>Measure 3 things at home in centimetres.</p>' }],
  submission: [],
  practice: [],
  competency: [],
}

const api = {
  'parent.dashboard': {
    subscription: { active: 1, status: 'Trial', plan: 'Free trial', until: '2026-11-13', max_learners: 3 },
    children: [
      { student: 'EDU-STU-0001', name: 'Amina Wanjiru', first_name: 'Amina', grade: 'Grade 4', learner_code: 'AMW-4821', enabled: 1, lessons_completed_this_week: 6, quiz_average_this_week: 78, last_active: '2026-10-30 08:12:00' },
      { student: 'EDU-STU-0002', name: 'Brian Kamau', first_name: 'Brian', grade: 'Grade 7', learner_code: 'BKA-1934', enabled: 1, lessons_completed_this_week: 2, quiz_average_this_week: null, last_active: '2026-10-27 19:30:00' },
    ],
  },
  'teacher.dashboard': { instructor_name: 'Peter Otieno', school: 'Kilimani Primary School', learners: 38, open_assignments: 3, to_review: 7, unanswered_feedback: 2, grades: [{ grade: 'Grade 4', learners: 21 }, { grade: 'Grade 5', learners: 17 }] },
  'tutor.conversations': [{ conversation: 'c1', topic: 'Fractions', messages: 4, last: '2026-10-29 18:02:00' }],
  'tutor.ask': (a) => ({ conversation: 'c2', interaction: 'i' + Date.now(), quota: { limit: 20, remaining: 17, used: 3 },
    answer: `Good question! Let us think about **${a.message.slice(0, 40)}** together.\n\n1. What do you already know?\n2. Try one small example.\n\nWhat do you get?` }),
  'tutor.practice': { practice: 'P1', title: 'Fractions practice', quota: {}, questions: [
    { question: 'What fraction of a pizza is left if 2 of 8 slices are eaten?', options: ['6/8', '2/8', '8/6', '1/8'], answer: 0, explanation: '8 − 2 = 6 slices are left, so 6/8.' },
    { question: 'Which is equal to 1/2?', options: ['2/4', '1/3', '3/4', '2/3'], answer: 0, explanation: '2/4 means 2 of 4 equal parts, the same as half.' },
  ] },
}

function command(cmd, args = {}) {
  switch (cmd) {
    case 'app_state':
      return { server: 'https://school.nergaa.cloud', session: sessions[role] ?? null, parent_waiting: false, pending: 1, last_sync: '2026-10-30 07:50:00', version: '0.2.0', platform: 'android' }
    case 'learner_status':
      return { learner, entitlement: { active: 1, status: 'Trial', until: '2026-11-13' }, ai_quota: { limit: 20, remaining: 17, used: 3, enabled: 1 }, last_sync: '2026-10-30 07:50:00', has_content: true, pending: 1 }
    case 'local_list': {
      const rows = content[args.kind] || []
      const field = parentField[args.kind]
      return args.parent && field ? rows.filter((r) => r[field] === args.parent) : rows
    }
    case 'local_get':
      return (content[args.kind] || []).find((r) => r.name === args.name) || null
    case 'local_quiz':
      return quizzes[args.name] || null
    case 'mine_list':
      return mine[args.kind] || []
    case 'queue_event':
      return { pending: 1 }
    case 'sync_now':
      return { pending: 0, last_sync: '2026-10-30 09:00:00', rejected: 0 }
    case 'outbox_list':
      return []
    case 'api': {
      const hit = api[args.path]
      const data = typeof hit === 'function' ? hit(args.args || {}) : hit ?? []
      return args.cacheKey ? { data, cached: false } : { data }
    }
    default:
      return null
  }
}

let nextCallback = 1
window.__TAURI_INTERNALS__ = {
  invoke: async (cmd, args) => {
    await new Promise((r) => setTimeout(r, 15))
    return command(cmd, args)
  },
  transformCallback: () => nextCallback++,
  metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
}
