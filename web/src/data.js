import { from } from './supabase.js'

export const excluded = /^(one piece|fairy tail)$/i
export const isExcluded = title => excluded.test(title?.trim() || '')
const orderKeys = { marquee_episode_completion_coverage: 'episode_id', marquee_movie_completion_coverage: 'movie_title_id', marquee_watchlist: 'title_id' }
export async function allRows(table, select = '*') {
  const rows = []
  for (let start = 0; ; start += 800) {
    const { data, error } = await from(table).select(select).order(orderKeys[table] || 'id').range(start, start + 799)
    if (error) throw error
    rows.push(...data)
    if (data.length < 800) return rows
  }
}
export async function loadLibrary() {
  const names = ['marquee_titles', 'marquee_seasons', 'marquee_episodes', 'marquee_episode_completion_coverage', 'marquee_movie_completion_coverage', 'marquee_watch_history', 'marquee_statuses', 'marquee_ratings', 'marquee_watchlist']
  const values = await Promise.all(names.map(name => allRows(name)))
  return Object.fromEntries(names.map((name, index) => [name.replace('marquee_', ''), values[index]]))
}
export function buildIndex(data) {
  const titles = data.titles.filter(t => !isExcluded(t.display_title))
  const seasons = new Map(data.seasons.map(s => [s.id, s]))
  const episodes = new Map(data.episodes.map(e => [e.id, e]))
  const coverage = new Map(data.episode_completion_coverage.map(c => [c.episode_id, c]))
  const movieCoverage = new Map(data.movie_completion_coverage.map(c => [c.movie_title_id, c]))
  const bySeason = new Map()
  for (const episode of data.episodes) {
    if (!bySeason.has(episode.season_id)) bySeason.set(episode.season_id, [])
    bySeason.get(episode.season_id).push(episode)
  }
  for (const entries of bySeason.values()) entries.sort((a,b) => (a.episode_number ?? 9999) - (b.episode_number ?? 9999))
  const byShow = new Map()
  for (const season of data.seasons) {
    if (!byShow.has(season.show_title_id)) byShow.set(season.show_title_id, [])
    byShow.get(season.show_title_id).push(season)
  }
  for (const entries of byShow.values()) entries.sort((a,b) => (a.season_number ?? 9999) - (b.season_number ?? 9999))
  const statuses = new Map(data.statuses.filter(s => s.title_id).map(s => [s.title_id,s]))
  const seasonStatuses = new Map(data.statuses.filter(s => s.season_id).map(s => [s.season_id,s]))
  const ratings = new Map(data.ratings.filter(r => r.title_id).map(r => [r.title_id,r]))
  const seasonRatings = new Map(data.ratings.filter(r => r.season_id).map(r => [r.season_id,r]))
  const watchlist = new Map(data.watchlist.map(w => [w.title_id,w]))
  const history = new Map()
  for (const event of data.watch_history) {
    const key = event.episode_id || event.movie_title_id
    if (!history.has(key)) history.set(key, [])
    history.get(key).push(event)
  }
  for (const entries of history.values()) entries.sort((a,b) => b.watched_at.localeCompare(a.watched_at))
  const progress = t => {
    if (t.media_type === 'movie') return { done: movieCoverage.has(t.id) ? 1 : 0, total: 1 }
    const items = (byShow.get(t.id) || []).flatMap(s => bySeason.get(s.id) || [])
    return {done: items.filter(e => coverage.has(e.id)).length, total: items.length}
  }
  return { titles, seasons, episodes, coverage, movieCoverage, bySeason, byShow, statuses, seasonStatuses, ratings, seasonRatings, watchlist, history, progress }
}
