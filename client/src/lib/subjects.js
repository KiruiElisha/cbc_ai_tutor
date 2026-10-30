/** One look per learning area (icon and colour), so a subject is recognisable on every screen. */

const THEMES = [
  ['Math', '➗', '#2563eb'],
  ['English', '📖', '#7c3aed'],
  ['Kiswahili', '🗣️', '#db2777'],
  ['Indigenous', '🗨️', '#c026d3'],
  ['Language', '🔤', '#7c3aed'],
  ['Integrated Science', '🔬', '#0891b2'],
  ['Science', '🔬', '#0891b2'],
  ['Physics', '🧲', '#0891b2'],
  ['Chemistry', '⚗️', '#0e7490'],
  ['Biology', '🧬', '#059669'],
  ['Social', '🌍', '#ea580c'],
  ['Geography', '🗺️', '#ea580c'],
  ['History', '🏛️', '#b45309'],
  ['Agriculture', '🌱', '#16a34a'],
  ['Environmental', '🌳', '#16a34a'],
  ['Creative', '🎨', '#e11d48'],
  ['Physical', '⚽', '#dc2626'],
  ['Religious', '🕊️', '#4f46e5'],
  ['Pre-Technical', '🛠️', '#475569'],
  ['Computer', '💻', '#334155'],
  ['Business', '💼', '#0f766e'],
  ['Community', '🤝', '#0d9488'],
]

export function subject(title = '') {
  const hit = THEMES.find(([key]) => title.includes(key))
  const [, icon, color] = hit || ['', '📘', '#0f766e']
  return { icon, color, style: `--c: ${color}` }
}
