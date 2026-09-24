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

export function getContinueTitle(index) {
  const watching = index.titles.filter(title => title.media_type === 'show' && (
    index.statuses.get(title.id)?.status === 'watching' ||
    (index.byShow.get(title.id) || []).some(season => index.seasonStatuses.get(season.id)?.status === 'watching')
  ))
  if (!watching.length) return null
  const ordered = watching.map(title => {
    const episodes = (index.byShow.get(title.id) || []).flatMap(season => index.bySeason.get(season.id) || [])
    const next = episodes.find(episode => !index.coverage.has(episode.id)) || null
    const recent = episodes.reduce((latest, episode) => {
      const watched = index.history.get(episode.id)?.[0]?.watched_at
      return watched && watched > latest ? watched : latest
    }, '')
    return { title, next, recent }
  }).sort((a,b) => (Number(Boolean(b.next)) - Number(Boolean(a.next))) || b.recent.localeCompare(a.recent) || a.title.display_title.localeCompare(b.title.display_title))
  return ordered[0]
}
