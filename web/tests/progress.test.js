import test from 'node:test'
import assert from 'node:assert/strict'
import {buildIndex,isExcluded} from '../src/data.js'
test('one canonical episode counts once with dated and undated evidence',()=>{
 const state={titles:[{id:'show',display_title:'The Great Cleric',media_type:'show'},{id:'excluded',display_title:'One Piece',media_type:'show'}],seasons:[{id:'s1',show_title_id:'show',season_number:1}],episodes:[{id:'e1',season_id:'s1',episode_number:1},{id:'e2',season_id:'s1',episode_number:2}],episode_completion_coverage:[{episode_id:'e1',has_dated_watch:true,has_undated_completion:true}],movie_completion_coverage:[],watch_history:[{episode_id:'e1',watched_at:'2026-09-24T12:00:00Z',source:'manual'},{episode_id:'e1',watched_at:'2026-01-01T12:00:00Z',source:'trakt'}],statuses:[],ratings:[],watchlist:[]}
 const ix=buildIndex(state)
 assert.deepEqual(ix.progress(ix.titles[0]),{done:1,total:2})
 assert.equal(ix.titles.length,1)
 assert.equal(ix.history.get('e1').length,2)
 assert.equal(isExcluded('Fairy Tail'),true)
})
