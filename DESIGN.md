# Marquee design reference

Marquee is a personal screen journal for picking up a show, checking an episode, and seeing what was watched. Use GameDeck as a reference for owner-only sign-in, straightforward bottom navigation, and the GitHub → Vercel preview → review workflow; Marquee has its own visual voice.

## Current direction

- Phone first. The existing UI caps content at about 650px, uses a fixed bottom tab bar with iPhone safe-area padding, and keeps library, explore, watchlist, and activity available from that bar. Keep primary actions reachable and text legible at 375–393px.
- Quiet, dark screen-journal palette: near-black/navy surfaces, off-white text, muted secondary copy, warm gold for progress and actions. Editorial serif headings contrast with compact sans-serif metadata. These describe the current implementation, not a final brand approval.
- Progress must mean distinct canonical titles/episodes. Show `completed / cataloged` at show and season levels; link episodes to their evidence. Avoid implying that an undated historical completion occurred on a particular day.
- Separate source meanings in the UI: `Trakt` dated watch, `You` manual check-in, `Crunchyroll · source-reported date` for eligible promptly observed activity, and `Historical completion · date unverified` for older evidence. A source-reported date is not independently verified.
- Support loading, empty, failed, and saved states, visible keyboard focus, comfortable tap targets, and reduced motion. Check an iPhone viewport and the narrowest supported width after substantial changes.

## Before changing direction

Inspect the current `web/src/App.jsx` and `web/src/style.css`, and compare GameDeck's patterns where relevant. Use `.agents/skills/interface-design/SKILL.md` to establish a specific direction, `.agents/skills/react-best-practices/SKILL.md` during implementation, and `.agents/skills/web-design-guidelines/SKILL.md` for review. Record any approved enduring design decisions here instead of silently replacing these notes.
