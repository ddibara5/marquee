const KEY = 'marquee-accent-v1'
const accents = new Set(['red', 'blue'])

export function getAccent() {
  try {
    const saved = localStorage.getItem(KEY)
    return accents.has(saved) ? saved : 'red'
  } catch {
    return 'red'
  }
}

export function applyAccent(accent) {
  const value = accents.has(accent) ? accent : 'red'
  document.documentElement.dataset.accent = value
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '#0b1018')
  return value
}

export function saveAccent(accent) {
  const value = applyAccent(accent)
  try { localStorage.setItem(KEY, value) } catch { /* Keep the choice for this session. */ }
  return value
}
