# Marquee design reference

Marquee is a personal screen journal for picking up a show, checking an episode, and seeing what was watched. Use GameDeck as a reference for owner-only sign-in and straightforward bottom navigation. Routine UI changes publish from `main` to a stable production URL; use a branch preview when the owner requests separate review. Marquee has its own visual voice.

## Approved first-pass direction (2026-09-24)

- Phone first. The bottom bar has **Library, Activity, Insights**. Library opens on the collection, with a compact Up next entry when a show is marked watching. Search can also find the broader catalog. Watchlist and Explore do not get a first-pass page; saved data is preserved.
- Dark theater/game feel with one luminous accent. **Signal red is the default**; Settings (44px gear in the top-right header) offers Electric blue as a device-local alternative. The preference applies before first paint. The accent is a functional signal for progress, selection, and actions; neutral surfaces and readable off-white type carry the content.
- Settings stays small: Appearance and Sign out. It uses a native modal for focus handling and Escape dismissal. GameDeck supplies the gear/Settings interaction reference; Marquee does not need GameDeck's many theme families or settings categories.
- Insights is an actual tab with only defensible current metrics: unique canonical episodes with dated activity this month, shows marked watching, and distinct completed cataloged episodes. The monthly count excludes undated history. The mockup numbers were illustrative and are not shipped.
- Activity has source filter chips (All, Trakt, Crunchyroll, You) and per-row source labels. It has no opening provenance notice.
- The screen remains within roughly 650px on desktop; bottom navigation and settings respect iPhone safe areas. Keep primary actions reachable and text legible at 375–393px.
- Progress must mean distinct canonical titles/episodes. Show `completed / cataloged` at show and season levels; link episodes to their evidence. Avoid implying that an undated historical completion occurred on a particular day.
- Separate source meanings in the UI: `Trakt` dated watch, `You` manual check-in, `Crunchyroll · source-reported date` for eligible promptly observed activity, and `Historical completion · date unverified` for older evidence. A source-reported date is not independently verified.
- Support loading, empty, failed, and saved states, visible keyboard focus, comfortable tap targets, and reduced motion. Check an iPhone viewport and the narrowest supported width after substantial changes.

## Before changing direction

Inspect the current `web/src/App.jsx` and `web/src/style.css`, and compare GameDeck's patterns where relevant. Use `.agents/skills/interface-design/SKILL.md` to refine the direction, `.agents/skills/react-best-practices/SKILL.md` during implementation, and `.agents/skills/web-design-guidelines/SKILL.md` for review. Record later approved enduring design decisions here.
