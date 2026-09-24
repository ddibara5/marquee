import assert from 'node:assert/strict'
import test from 'node:test'
import { buildIndex } from '../src/data.js'
import { buildInsights, getContinueTitle } from '../src/insights.js'

test('insights count canonical episodes once and exclude undated-only and excluded shows', () => {
  const state = {
    titles: [
      { id:'show', display_title:'The Great Cleric', media_type:'show' },
      { id:'other', display_title:'Silo', media_type:'show' },
      { id:'excluded', display_title:'One Piece', media_type:'show' },
    ],
    seasons: [
      { id:'s1', show_title_id:'show', season_number:1 },
      { id:'s2', show_title_id:'other', season_number:1 },
      { id:'sx', show_title_id:'excluded', season_number:1 },
    ],
    episodes: [
      { id:'e1', season_id:'s1', episode_number:1 },
      { id:'e2', season_id:'s1', episode_number:2 },
      { id:'e3', season_id:'s1', episode_number:3 },
      { id:'ex', season_id:'sx', episode_number:1 },
    ],
    episode_completion_coverage: [
      { episode_id:'e1', has_dated_watch:true, has_undated_completion:true },
      { episode_id:'e2', has_dated_watch:false, has_undated_completion:true },
      { episode_id:'ex', has_dated_watch:true },
    ],
    movie_completion_coverage: [],
    watch_history: [
      { episode_id:'e1', source:'trakt', watched_at:'2026-09-23T23:30:00Z' },
      { episode_id:'e1', source:'crunchyroll', watched_at:'2026-09-24T00:10:00Z' },
      { episode_id:'ex', source:'manual', watched_at:'2026-09-24T12:00:00Z' },
    ],
    statuses: [
      { title_id:'show', status:'watching' },
      { season_id:'s1', status:'watching' },
      { title_id:'excluded', status:'watching' },
    ], ratings:[], watchlist:[],
  }
  const index = buildIndex(state)
  const result = buildInsights(state,index,new Date('2026-09-26T12:00:00Z'))
  assert.equal(result.datedThisMonth,1)
  assert.equal(result.completedCataloged,2)
  assert.deepEqual(result.watching.map(show => show.id),['show'])
  assert.equal(getContinueTitle(index)?.next?.id,'e3')
})
