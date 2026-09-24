import { from } from './supabase.js'

export const excluded = /^(one piece|fairy tail)$/i
export const isExcluded = title => excluded.test(title?.trim() || '')
const orderKeys = { marquee_episode_completion_coverage: 'episode_id', marquee_movie_completion_coverage: 'movie_title_id', marquee_watchlist: 'title_id', marquee_verified_season_totals: 'season_id', marquee_season_release_schedules: 'season_id' }
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
  const names = ['marquee_titles', 'marquee_seasons', 'marquee_episodes', 'marquee_episode_completion_coverage', 'marquee_movie_completion_coverage', 'marquee_watch_history', 'marquee_statuses', 'marquee_ratings', 'marquee_verified_season_totals', 'marquee_season_release_schedules']
  const values = await Promise.all(names.map(name => allRows(name)))
  return Object.fromEntries(names.map((name, index) => [name.replace('marquee_', ''), values[index]]))
}
export function buildIndex(data, now = new Date()) {
  const titles = data.titles.filter(t => !isExcluded(t.display_title))
  const seasons = new Map(data.seasons.map(s => [s.id, s]))
  const episodes = new Map(data.episodes.map(e => [e.id, e]))
  const coverage = new Map(data.episode_completion_coverage.map(c => [c.episode_id, c]))
  const verifiedTotals = new Map((data.verified_season_totals || []).map(row => [row.season_id, row.episode_total]))
  const releaseSchedules = new Map((data.season_release_schedules || []).map(row => [row.season_id, row]))
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
  const watchlist = new Map((data.watchlist || []).map(w => [w.title_id,w]))
  const history = new Map()
  for (const event of data.watch_history) {
    const key = event.episode_id || event.movie_title_id
    if (!history.has(key)) history.set(key, [])
    history.get(key).push(event)
  }
  for (const entries of history.values()) entries.sort((a,b) => b.watched_at.localeCompare(a.watched_at))
  const seasonProgress = season => {
    const items = bySeason.get(season.id) || []
    const done = items.filter(e => coverage.has(e.id)).length
    const schedule = releaseSchedules.get(season.id)
    const first = schedule && Date.parse(`${schedule.first_release_on}T00:00:00Z`)
    const released = first && now.getTime() >= first ? Math.min(schedule.planned_episodes, 1 + Math.floor((now.getTime() - first) / (schedule.interval_days * 86400000))) : 0
    const total = schedule ? released || null : verifiedTotals.get(season.id) ?? null
    return { done, total, recorded: items.length, kind: schedule ? 'released' : total ? 'reviewed' : null, planned: schedule?.planned_episodes ?? null }
  }
  const progress = t => {
    if (t.media_type === 'movie') return { done: movieCoverage.has(t.id) ? 1 : 0, total: 1 }
    const seasonsForShow = byShow.get(t.id) || []
    const recorded = seasonsForShow.reduce((sum, s) => sum + seasonProgress(s).done, 0)
    const recent = seasonsForShow.map(season => ({ season, watched: (bySeason.get(season.id) || []).reduce((latest, episode) => {
      const timestamp = history.get(episode.id)?.[0]?.watched_at || ''
      return timestamp > latest ? timestamp : latest
    }, '') })).filter(item => item.watched).sort((a,b) => b.watched.localeCompare(a.watched))[0]?.season
    const focus = recent || [...seasonsForShow].reverse().find(s => seasonProgress(s).done)
    return { ...seasonProgress(focus || { id: '' }), season: focus, recorded }
  }
  return { titles, seasons, episodes, coverage, movieCoverage, verifiedTotals, releaseSchedules, bySeason, byShow, statuses, seasonStatuses, ratings, seasonRatings, watchlist, history, seasonProgress, progress }
}
