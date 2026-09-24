import { useEffect, useMemo, useRef, useState } from 'react'
import { auth, from, ownerEmail } from './supabase.js'
import { loadLibrary, buildIndex } from './data.js'
import { buildInsights, getContinueTitle } from './insights.js'
import { getAccent, saveAccent } from './theme.js'

const statuses = { planned: 'Plan to watch', watching: 'Watching', completed: 'Completed', on_hold: 'On hold', dropped: 'Dropped' }
const date = value => new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value))
const covers = [['#65445b','#26283c'],['#526679','#1b3041'],['#795749','#353042'],['#50685f','#22383e'],['#756449','#313a4d']]
const sourceLabel = source => source === 'manual' ? 'You · manual check-in' : source === 'trakt' ? 'Trakt · dated watch' : 'Crunchyroll · source-reported date'

function Cover({ title, large = false }) {
  const colors = covers[title.display_title.length % covers.length]
  return <span className={`cover${large ? ' cover-large' : ''}`} style={{ '--cover-a': colors[0], '--cover-b': colors[1] }} aria-hidden="true">
    <span className="cover-type">{title.is_anime ? 'ANIME' : title.media_type === 'movie' ? 'FILM' : 'SERIES'}</span>
    <strong>{title.display_title}</strong>
  </span>
}
function Bar({ done, total }) {
  if (!total) return null
  return <span className="bar" role="img" aria-label={`${done} of ${total} reviewed season episodes complete`}><span style={{ width: `${Math.min(100, done / total * 100)}%` }} /></span>
}
const progressText = progress => progress.total ? `S${progress.season?.season_number ?? '–'} · ${progress.done} of ${progress.total} reviewed` : `${progress.recorded || 0} episodes recorded`
function GearIcon() {
  return <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3.1"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6 2 2 0 0 1-4 0 1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3 2 2 0 1 1-2.8-2.8 1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1 2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9 2 2 0 1 1 2.8-2.8 1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3a2 2 0 1 1 4 0 1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3 2 2 0 1 1 2.8 2.8 1.7 1.7 0 0 0-.3 1.9A1.7 1.7 0 0 0 21 10a2 2 0 1 1 0 4 1.7 1.7 0 0 0-1.6 1Z"/></svg>
}
function Login() {
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  return <div className="login"><div className="login-brand">◇</div><small className="eyebrow">YOUR SCREEN JOURNAL</small><h1>Marquee</h1><p>Your stories, in one private place.</p>
    <form onSubmit={async event => { event.preventDefault(); const { error } = await auth.signInWithPassword({ email: ownerEmail, password }); if (error) setMessage(error.message) }}><label>GameDeck password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label><button className="primary">Sign in</button></form>
    <button className="text-button" onClick={async () => { const { error } = await auth.signInWithOtp({ email: ownerEmail, options: { emailRedirectTo: location.origin } }); setMessage(error?.message || 'Check your email. This preview URL must be allowed in Supabase Auth redirects.') }}>Email me a sign-in link</button>{message && <p role="alert">{message}</p>}</div>
}
function Evidence({ history = [], undated }) {
  return <section className="evidence"><h2>Watch record</h2>{undated && <div className="evidence-row"><strong>✓ {history.some(h => h.source === 'crunchyroll') ? 'Completion evidence' : 'Historical completion'}</strong><small>{history.some(h => h.source === 'crunchyroll') ? 'Original source evidence retained · progress counts once' : 'Date unverified · counts once toward progress'}</small></div>}{history.map(h => <div className="evidence-row" key={h.id}><strong>◷ {date(h.watched_at)}</strong><small>{sourceLabel(h.source)}</small></div>)}{!undated && !history.length && <p className="muted">No completion recorded.</p>}</section>
}
function Settings({ dialogRef, onClose, accent, onAccent, onSignOut }) {
  return <dialog className="settings-dialog" ref={dialogRef} aria-label="Settings" onClose={onClose}>
    <div className="settings-content"><div className="settings-header"><button className="settings-back" onClick={onClose} aria-label="Close settings">‹</button><h2>Settings</h2></div><div className="settings-body"><div className="eyebrow">APPEARANCE</div><h3>Signal color</h3><p className="muted">Choose the accent used throughout Marquee. This preference is saved on this device.</p>
      <div className="theme-choices" role="radiogroup" aria-label="Signal color">
        {[['red','Signal red','#ff5a69'],['blue','Electric blue','#55d9ff']].map(([value,label,swatch]) =>
          <label key={value} className={`theme-choice${accent === value ? ' chosen' : ''}`}>
            <input type="radio" name="marquee-accent" value={value} checked={accent === value} onChange={() => onAccent(value)} />
            <span className="theme-swatch" style={{ '--swatch': swatch }} aria-hidden="true"><span /></span>
            <span className="theme-label"><strong>{label}</strong><small>Dark theater · {value === 'red' ? 'warm signal' : 'cool signal'}</small></span>
            <span className="selection-mark" aria-hidden="true">{accent === value ? '✓' : ''}</span>
          </label>)}
      </div>
      <div className="settings-account"><span className="eyebrow">ACCOUNT</span><button className="account-row" onClick={onSignOut}><span>Sign out</span><span aria-hidden="true">›</span></button></div>
    </div></div>
  </dialog>
}
function TitleRow({ title, index, onOpen }) {
  const progress = index.progress(title)
  return <button className="title-row" onClick={() => onOpen(title.id)}><Cover title={title}/><span className="row-copy"><strong>{title.display_title}</strong><small>{title.is_anime ? 'Anime' : title.media_type === 'movie' ? 'Film' : 'Series'}{title.release_year ? ` · ${title.release_year}` : ''}</small><span className="row-progress">{title.media_type === 'show' && <Bar {...progress}/>}<span>{title.media_type === 'movie' ? (progress.done ? 'Watched' : 'Unwatched') : progress.recorded ? progressText(progress) : 'Episodes pending'}</span></span></span><span className="chevron" aria-hidden="true">›</span></button>
}
function Library({ index, filter, setFilter, query, setQuery, onOpen }) {
  const personal = index.titles.filter(title => (index.progress(title).recorded || index.progress(title).done) || index.statuses.has(title.id) || (index.byShow.get(title.id) || []).some(season => index.seasonStatuses.has(season.id)))
  const pool = query.trim() ? index.titles : personal
  const listed = pool.filter(title => (filter === 'All' || (filter === 'Anime' && title.is_anime) || (filter === 'Series' && title.media_type === 'show' && !title.is_anime) || (filter === 'Films' && title.media_type === 'movie') || (filter === 'In progress' && (index.statuses.get(title.id)?.status === 'watching' || (index.byShow.get(title.id) || []).some(season => index.seasonStatuses.get(season.id)?.status === 'watching')))) && title.display_title.toLowerCase().includes(query.trim().toLowerCase())).sort((a,b) => a.display_title.localeCompare(b.display_title))
  const resume = getContinueTitle(index)
  return <><div className="eyebrow">YOUR PERSONAL COLLECTION</div><h1 className="page-title">Your library.</h1><p className="page-subtitle">Find a story and pick up where you left off.</p>
    {resume && <><div className="section-head"><h2>Up next</h2></div><button className="resume" onClick={() => onOpen(resume.title.id, resume.season.id, resume.next?.id)}><Cover title={resume.title}/><span className="resume-copy"><small>{resume.next ? `Continue · Episode ${resume.next.episode_number ?? 'Special'}` : `Season ${resume.season.season_number ?? 'specials'} · ${resume.progress.done} of ${resume.progress.total} reviewed`}</small><strong>{resume.title.display_title}</strong><Bar {...resume.progress}/></span><span className="chevron" aria-hidden="true">›</span></button></>}
    <label className="search"><span className="search-icon" aria-hidden="true"/><input aria-label="Search your library and catalog" name="marquee-search" autoComplete="off" placeholder="Search your library and catalog…" value={query} onChange={event => setQuery(event.target.value)}/></label>
    <div className="chips" role="group" aria-label="Library filter">{['All','Anime','Series','Films','In progress'].map(option => <button key={option} aria-pressed={filter === option} className={filter === option ? 'active' : ''} onClick={() => setFilter(option)}>{option}</button>)}</div>
    <div className="section-head"><h2>{query.trim() ? 'Search results' : 'Your collection'}</h2><small>{listed.length} {listed.length === 1 ? 'title' : 'titles'}</small></div><div className="list">{listed.map(title => <TitleRow title={title} index={index} onOpen={onOpen} key={title.id}/>)}{!listed.length && <div className="empty">{query.trim() ? 'No titles match this search.' : 'Your collection is empty. Search the catalog to start tracking.'}</div>}</div>
  </>
}
function Activity({ index, data, sourceFilter, setSourceFilter, onOpen }) {
  const entries = data.watch_history.filter(h => sourceFilter === 'All' || h.source === ({ You: 'manual' }[sourceFilter] || sourceFilter.toLowerCase())).map(h => {
    const episode = index.episodes.get(h.episode_id), season = index.seasons.get(episode?.season_id)
    const title = index.titles.find(t => t.id === (h.movie_title_id || season?.show_title_id))
    return title ? { history: h, episode, season, title } : null
  }).filter(Boolean).sort((a,b) => b.history.watched_at.localeCompare(a.history.watched_at)).slice(0,80)
  return <><div className="eyebrow">A RECORD OF WHAT YOU WATCHED</div><h1 className="page-title">Activity.</h1><p className="page-subtitle">Dated watches and check-ins, newest first.</p><div className="chips activity-chips" role="group" aria-label="Activity source">{['All','Trakt','Crunchyroll','You'].map(option => <button key={option} aria-pressed={sourceFilter === option} className={sourceFilter === option ? 'active' : ''} onClick={() => setSourceFilter(option)}>{option}</button>)}</div>
    <div className="section-head"><h2>Recent watches</h2></div><div className="list">{entries.map(({ history, episode, season, title }) => <button className="activity-row" key={history.id} onClick={() => onOpen(title.id, season?.id, episode?.id)}><span className="activity-dot" aria-hidden="true"/><span className="row-copy"><strong>{title.display_title}</strong><small>{episode ? `S${season?.season_number ?? '–'} · ${episode.episode_number ? `E${episode.episode_number}` : 'Special'}${episode.display_title ? ` · ${episode.display_title}` : ''}` : 'Film'}<br/>{sourceLabel(history.source)}</small></span><time dateTime={history.watched_at}>{date(history.watched_at)}</time></button>)}{!entries.length && <div className="empty">No dated watches from this source yet. Historical completions still count toward library progress.</div>}</div>
  </>
}
function Insights({ index, data, onOpen }) {
  const insight = buildInsights(data, index)
  return <><div className="eyebrow">ONLY WHAT YOUR RECORDS SUPPORT</div><h1 className="page-title">Insights.</h1><p className="page-subtitle">A small snapshot of progress, without guesses.</p>
    <div className="insight-hero"><small>Dated episodes · this month</small><strong>{insight.datedThisMonth} <span>{insight.datedThisMonth === 1 ? 'episode' : 'episodes'}</span></strong><p>Distinct episodes with a Trakt watch, your check-in, or a promptly observed Crunchyroll date.</p></div>
    <div className="stat-grid"><div className="stat"><small>Shows marked watching</small><strong>{insight.watching.length}</strong><small>From your current statuses</small></div><div className="stat"><small>Cataloged episodes complete</small><strong>{insight.completedCataloged}</strong><small>Each episode counted once</small></div></div>
    {insight.watching.length > 0 && <><div className="section-head"><h2>In progress</h2></div><div className="list">{insight.watching.slice(0,5).map(title => <TitleRow title={title} index={index} onOpen={onOpen} key={title.id}/>)}</div></>}
    <p className="insight-note">Historical completions with unverified dates count toward progress, but never toward monthly dated activity.</p>
  </>
}
function TitleDetail({ title, index, onSeason, onMovieCheckIn, busy, onSave }) {
  const progress = index.progress(title)
  return <><div className="title-hero"><Cover title={title} large/><div><div className="eyebrow">{title.is_anime ? 'ANIME' : title.media_type === 'movie' ? 'FILM' : 'SERIES'}{title.release_year ? ` · ${title.release_year}` : ''}</div><h1>{title.display_title}</h1>{title.media_type === 'show' && <Bar {...progress}/>}<small>{title.media_type === 'movie' ? (progress.done ? 'Watched' : 'Not watched') : progressText(progress)}</small></div></div>
    {title.synopsis && <p className="synopsis">{title.synopsis}</p>}
    {title.media_type === 'movie' && <button className="primary full" disabled={busy} onClick={() => onMovieCheckIn(title)}>+ Log a watch</button>}
    <div className="controls"><label>Status<select value={index.statuses.get(title.id)?.status || ''} disabled={busy} onChange={event => onSave('marquee_statuses','title_id',title.id,'status',event.target.value)}><option value="" disabled>Choose status</option>{Object.entries(statuses).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Rating · out of 10<select value={index.ratings.get(title.id)?.score || ''} disabled={busy} onChange={event => onSave('marquee_ratings','title_id',title.id,'score',Number(event.target.value))}><option value="" disabled>Choose rating</option>{Array.from({ length: 20 }, (_,i) => (i+1)/2).map(score => <option key={score} value={score}>{score}</option>)}</select></label></div>
    {title.media_type === 'movie' ? <Evidence history={index.history.get(title.id)} undated={index.movieCoverage.get(title.id)?.has_undated_completion}/> : <><div className="section-head"><h2>Seasons</h2><small>{(index.byShow.get(title.id) || []).length}</small></div><div className="list">{(index.byShow.get(title.id) || []).map(season => { const { done, total } = index.seasonProgress(season); return <button className="season-row" key={season.id} onClick={() => onSeason(season.id)}><span className="number">{season.season_number === null ? 'SP' : String(season.season_number).padStart(2,'0')}</span><span className="row-copy"><strong>{season.display_title || `Season ${season.season_number ?? 'Specials'}`}</strong><small>{total ? `${done} of ${total} reviewed episodes` : done ? `${done} episodes recorded · total unknown` : statuses[index.seasonStatuses.get(season.id)?.status] || 'Episodes pending'}</small><Bar done={done} total={total}/></span><span className="chevron" aria-hidden="true">›</span></button> })}</div></>}
  </>
}
function SeasonDetail({ title, season, index, onEpisode, busy, onSave }) {
  const episodes = index.bySeason.get(season.id) || [], { done, total } = index.seasonProgress(season)
  return <><div className="eyebrow">{title.display_title}</div><h1 className="detail-title">{season.display_title || `Season ${season.season_number ?? 'Specials'}`}</h1><p className="muted">{total ? `${done} of ${total} reviewed episodes complete` : `${done} episodes recorded · season total unknown`}</p><Bar done={done} total={total}/>
    <div className="controls"><label>Season status<select value={index.seasonStatuses.get(season.id)?.status || ''} disabled={busy} onChange={event => onSave('marquee_statuses','season_id',season.id,'status',event.target.value)}><option value="" disabled>Choose status</option>{Object.entries(statuses).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>Season rating<select value={index.seasonRatings.get(season.id)?.score || ''} disabled={busy} onChange={event => onSave('marquee_ratings','season_id',season.id,'score',Number(event.target.value))}><option value="" disabled>Choose rating</option>{Array.from({ length:20 },(_,i)=>(i+1)/2).map(score => <option key={score} value={score}>{score}</option>)}</select></label></div>
    <div className="section-head"><h2>Episodes</h2></div><div className="list">{episodes.map(ep => <button className="episode-row" key={ep.id} onClick={() => onEpisode(ep.id)}><span className={`number${index.coverage.has(ep.id) ? ' done' : ''}`}>{index.coverage.has(ep.id) ? '✓' : ep.episode_number ?? '★'}</span><span className="row-copy"><strong>{ep.display_title || `Episode ${ep.episode_number ?? 'Special'}`}</strong><small>{index.coverage.get(ep.id)?.has_dated_watch ? 'Dated watch' : index.coverage.get(ep.id)?.has_undated_completion ? 'Complete · date unverified' : ep.aired_at ? `Aired ${date(ep.aired_at)}` : 'Not marked complete'}</small></span><span className="chevron" aria-hidden="true">›</span></button>)}</div>
  </>
}
function EpisodeDetail({ title, season, episode, index, onCheckIn, busy }) {
  return <><div className="eyebrow">{title.display_title} · {season.display_title || `Season ${season.season_number ?? 'Specials'}`}</div><h1 className="detail-title">{episode.display_title || `Episode ${episode.episode_number ?? 'Special'}`}</h1><p className="muted">{[episode.episode_number ? `Episode ${episode.episode_number}` : null, episode.runtime_minutes ? `${episode.runtime_minutes} min` : null, episode.aired_at ? `Aired ${date(episode.aired_at)}` : null].filter(Boolean).join(' · ')}</p><Evidence history={index.history.get(episode.id)} undated={index.coverage.get(episode.id)?.has_undated_completion}/><button className="primary full" disabled={busy} onClick={() => onCheckIn(episode)}>+ Check in this episode now</button><p className="footnote">This records a new dated watch. Progress still counts this canonical episode once across all sources.</p></>
}
export default function App() {
  const [session,setSession] = useState(undefined), [data,setData] = useState(null), [error,setError] = useState(''), [busy,setBusy] = useState(false)
  const [tab,setTab] = useState('Library'), [filter,setFilter] = useState('All'), [query,setQuery] = useState(''), [sourceFilter,setSourceFilter] = useState('All')
  const [titleId,setTitle] = useState(null), [seasonId,setSeason] = useState(null), [episodeId,setEpisode] = useState(null), [toast,setToast] = useState('')
  const [settingsOpen,setSettingsOpen] = useState(false), [accent,setAccent] = useState(getAccent)
  const dialogRef = useRef(null)
  useEffect(() => { let live = true; auth.getSession().then(({data:result}) => { if (live) setSession(result.session?.user?.email?.toLowerCase() === ownerEmail ? result.session : null) }).catch(e => { if (live) { setSession(null); setError(e.message) } }); const { data: listener } = auth.onAuthStateChange((_,next) => { if (live) setSession(next?.user?.email?.toLowerCase() === ownerEmail ? next : null) }); return () => { live = false; listener.subscription.unsubscribe() } }, [])
  async function refresh() { try { setData(await loadLibrary()); setError('') } catch(e) { setError(e.message) } }
  useEffect(() => { if (session) refresh(); else setData(null) }, [session?.user?.id])
  useEffect(() => { const dialog = dialogRef.current; if (!dialog) return; if (settingsOpen && !dialog.open) dialog.showModal(); else if (!settingsOpen && dialog.open) dialog.close() }, [settingsOpen,session?.user?.id])
  function closeDetail() { if (episodeId) setEpisode(null); else if (seasonId) setSeason(null); else setTitle(null) }
  useEffect(() => { function onKey(event) { if (event.key === 'Escape' && !settingsOpen) closeDetail() } window.addEventListener('keydown',onKey); return () => window.removeEventListener('keydown',onKey) }, [episodeId,seasonId,titleId,settingsOpen])
  async function mutation(task,message) { setBusy(true); setError(''); try { await task(); await refresh(); setToast(message); window.setTimeout(() => setToast(''),3500) } catch(e) { setError(e.message) } finally { setBusy(false) } }
  function save(table,column,id,field,value) { mutation(async () => { const old = data[table.replace('marquee_','')].find(entry => entry[column] === id); const payload = { user_id:session.user.id,[column]:id,[field]:value,source:'manual',manual_locked:true,updated_at:new Date().toISOString() }; const { error:failure } = old ? await from(table).update(payload).eq('id',old.id) : await from(table).insert(payload); if (failure) throw failure }, 'Saved') }
  function checkIn(target,column) { mutation(async () => { const {error:failure} = await from('marquee_watch_history').insert({user_id:session.user.id,[column]:target.id,source:'manual',watched_at:new Date().toISOString(),logical_event_key:`manual:${crypto.randomUUID()}`}); if (failure) throw failure }, 'Watch recorded · progress counts this title once') }
  const index = useMemo(() => data ? buildIndex(data) : null,[data])
  const title = index?.titles.find(item => item.id === titleId), season = index?.seasons.get(seasonId), episode = index?.episodes.get(episodeId)
  function openTitle(id,sid=null,eid=null) { setTitle(id); setSeason(sid); setEpisode(eid); window.scrollTo(0,0) }
  if (session === undefined) return <div className="loading">◇ Marquee</div>
  if (!session) return <Login/>
  if (!index) return <div className="loading">{error ? <><p>{error}</p><button onClick={refresh}>Try again</button></> : 'Opening your library…'}</div>
  return <div className="app"><a className="skip-link" href="#main-content">Skip to content</a><header className="app-header"><div className="wordmark"><span>◇</span> MARQUEE</div><button className="gear" aria-label="Settings" title="Settings" onClick={() => setSettingsOpen(true)}><GearIcon/></button></header>
    <main id="main-content">{title ? <><button className="back" onClick={closeDetail}>‹ {episode ? 'Season' : season ? title.display_title : tab}</button>{episode && season ? <EpisodeDetail title={title} season={season} episode={episode} index={index} onCheckIn={ep => checkIn(ep,'episode_id')} busy={busy}/> : season ? <SeasonDetail title={title} season={season} index={index} onEpisode={setEpisode} busy={busy} onSave={save}/> : <TitleDetail title={title} index={index} onSeason={setSeason} onMovieCheckIn={movie => checkIn(movie,'movie_title_id')} busy={busy} onSave={save}/>}</> : tab === 'Library' ? <Library index={index} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} onOpen={openTitle}/> : tab === 'Activity' ? <Activity index={index} data={data} sourceFilter={sourceFilter} setSourceFilter={setSourceFilter} onOpen={openTitle}/> : <Insights index={index} data={data} onOpen={openTitle}/>}
      {error && <div className="alert" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}{toast && <div className="toast" role="status">{toast}</div>}</main>
    <nav className="bottom-nav" aria-label="Primary navigation">{[['Library','▤'],['Activity','◷'],['Insights','◇']].map(([name,glyph]) => <button key={name} className={tab === name && !title ? 'active' : ''} aria-current={tab === name && !title ? 'page' : undefined} onClick={() => { setTab(name); setTitle(null); setSeason(null); setEpisode(null); setFilter('All'); setQuery(''); window.scrollTo(0,0) }}><span aria-hidden="true">{glyph}</span>{name}</button>)}</nav>
    <Settings dialogRef={dialogRef} accent={accent} onAccent={value => setAccent(saveAccent(value))} onClose={() => setSettingsOpen(false)} onSignOut={() => { setSettingsOpen(false); auth.signOut() }}/>
  </div>
}
