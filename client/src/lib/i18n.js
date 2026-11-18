import { prefs } from './prefs.js'

/**
 * Kiswahili for the screens children use (menus, Learn, Mwalimu, lessons, quizzes, practice).
 * Strings are written in English in the code and looked up here; anything without a
 * translation shows in English. Choose the language in More → Display.
 */
const SW = {
  // menus
  Learn: 'Jifunze', Mwalimu: 'Mwalimu', Assignments: 'Kazi', Progress: 'Maendeleo', More: 'Zaidi',
  // home
  Today: 'Leo', 'Continue where you stopped': 'Endelea ulipoachia', "Today's practice": 'Mazoezi ya leo',
  'All caught up': 'Umemaliza yote', questions: 'maswali', 'to hand in': 'za kukabidhi', Go: 'Anza',
  'Learning areas': 'Maeneo ya kujifunza', 'Coming soon': 'Inakuja hivi karibuni', lessons: 'masomo', of: 'kati ya',
  'Ask Mwalimu': 'Muulize Mwalimu', 'Your tutor': 'Mwalimu wako', 'Maths drills': 'Mazoezi ya hesabu',
  'Works offline': 'Hufanya kazi bila mtandao', 'A timed mixed paper': 'Karatasi ya mtihani yenye muda',
  'days in a row': 'siku mfululizo', 'day in a row': 'siku moja mfululizo', 'Free trial until': 'Majaribio ya bure hadi', min: 'dakika', "today's goal": 'lengo la leo', "Let's learn something new today": 'Tujifunze kitu kipya leo',
  'Last synced': 'Ilisawazishwa', Sync: 'Sawazisha', 'to do': 'za kufanya', 'All done': 'Zote zimekamilika',
  // Mwalimu
  'Ask Mwalimu anything…': 'Muulize Mwalimu chochote…', 'How should I help?': 'Nikusaidie vipi?',
  'Just a hint': 'Dokezo tu', 'Step by step': 'Hatua kwa hatua', Simpler: 'Kwa urahisi', 'Quiz me': 'Niulize maswali',
  'Check my work': 'Angalia kazi yangu', Kiswahili: 'Kiswahili', 'New chat': 'Mazungumzo mapya',
  'Mwalimu is thinking': 'Mwalimu anafikiri', 'Working it out carefully': 'Anafikiria kwa makini',
  'Almost there, thanks for waiting': 'Karibu tayari, asante kwa kusubiri', Listen: 'Sikiliza', Copy: 'Nakili',
  'Earlier chats': 'Mazungumzo ya awali', 'questions left today': 'maswali yamebaki leo',
  'Explain it more simply': 'Eleza kwa urahisi zaidi', 'Give me a practice question': 'Nipe swali la mazoezi',
  'Show me step by step': 'Nionyeshe hatua kwa hatua', 'Talking about': 'Tunazungumzia', 'Open lesson': 'Fungua somo',
  'Feeling unsafe? Call 116 (free)': 'Huko salama? Piga 116 (bure)',
  // lessons and quizzes
  Next: 'Endelea', Back: 'Rudi', 'Read to me': 'Nisomee', 'Stop reading': 'Acha kusoma',
  'Show the whole lesson on one page': 'Onyesha somo lote ukurasa mmoja', 'Show one part at a time': 'Onyesha sehemu moja moja',
  "I'm done, take the quiz": 'Nimemaliza, fanya jaribio', "I've finished this lesson": 'Nimemaliza somo hili',
  Practice: 'Mazoezi', 'Stuck? Ask Mwalimu': 'Umekwama? Muulize Mwalimu', 'Stuck? Get a hint': 'Umekwama? Pata dokezo',
  'Check my answer': 'Angalia jibu langu', 'Next question': 'Swali linalofuata', 'See my score': 'Ona alama zangu',
  'Correct!': 'Sahihi!', 'Not quite: the right answer is marked green.': 'Si sahihi: jibu sahihi lina rangi ya kijani.',
  'Learn this next': 'Jifunze hili sasa', 'Learn this again': 'Jifunze hili tena', Done: 'Nimemaliza',
  'Try again': 'Jaribu tena', 'Back to lessons': 'Rudi kwa masomo', 'Question': 'Swali',
}

const lang = () => prefs().lang

export function t(text) {
  return lang() === 'sw' ? SW[text] ?? text : text
}
