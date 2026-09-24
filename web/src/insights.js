// Insights only count canonical episodes visible in Marquee. A source event is
// still kept in history, but a second source for one episode cannot inflate
// the monthly episode count or lifetime progress.
export function buildInsights(data, index, now = new Date()) {
  const visibleShows = index.titles.filter(title => title.media_type === 'show')
  const visibleEpisodes = new Set(visibleShows.flatMap(title =>
    (index.byShow.get(title.id) || []).flatMap(season =>
      (index.bySeason.get(season.id) || []).map(episode => episode.id)
    )
  ))
  const thisMonth = new Set(data.watch_history.filter(history => {
    if (!history.episode_id || !visibleEpisodes.has(history.episode_id)) return false
    const played = new Date(history.watched_at)
    return !Number.isNaN(played.getTime()) && played.getFullYear() === now.getFullYear() && played.getMonth() === now.getMonth()
  }).map(history => history.episode_id))
  const watching = visibleShows.filter(title =>
    index.statuses.get(title.id)?.status === 'watching' ||
    (index.byShow.get(title.id) || []).some(season => index.seasonStatuses.get(season.id)?.status === 'watching')
  )
  return {
    datedThisMonth: thisMonth.size,
    completedCataloged: [...visibleEpisodes].filter(id => index.coverage.has(id)).length,
    watching,
  }
}

export function getContinueTitle(index, now = new Date()) {
  const cutoff = now.getTime() - 30 * 24 * 60 * 60 * 1000
  const inactive = new Set(['completed', 'on_hold', 'dropped'])
  const candidates = index.titles.filter(title => title.media_type === 'show' && !inactive.has(index.statuses.get(title.id)?.status)).flatMap(title =>
    (index.byShow.get(title.id) || []).filter(season => !inactive.has(index.seasonStatuses.get(season.id)?.status)).map(season => {
      const progress = index.seasonProgress(season)
      if (!progress.total || progress.done >= progress.total) return null
      const episodes = index.bySeason.get(season.id) || []
      const next = episodes.find(episode => !index.coverage.has(episode.id) && (!episode.aired_at || new Date(episode.aired_at).getTime() <= now.getTime())) || null
      const recent = episodes.reduce((latest, episode) => {
        const watched = index.history.get(episode.id)?.[0]?.watched_at || ''
        return watched > latest ? watched : latest
      }, '')
      const time = new Date(recent).getTime()
      return time >= cutoff && time <= now.getTime() ? { title, season, progress, next, recent } : null
    }).filter(Boolean)
  ).sort((a,b) => b.recent.localeCompare(a.recent) || a.title.display_title.localeCompare(b.title.display_title))
  return candidates[0] || null
}
