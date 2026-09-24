# Marquee agent guide

Read `README.md`, `PROJECT_CONTEXT.md`, `docs/SOURCE_OF_TRUTH.md`, `docs/INGESTION_PLAN.md`, and `docs/RUNBOOK.md` before changing the app or data pipeline. Read `DESIGN.md` before visual changes. The repository is the shared reference for Codex, Muse, Claude, and other agents; `CLAUDE.md` points here.

## Product and workflow

- Marquee is a private, phone-first screen journal. `web/` is a Vite/React app deployed from GitHub to Vercel. For routine app and UI changes, commit directly to `main` so the production URL stays stable for saved sign-in. Check the deployed build and revert the commit if needed. Use a branch preview when Dave explicitly requests one or when a change needs separate review before production. Preserve owner-only Supabase authentication.
- Keep all new database objects `marquee_` scoped. Never modify GameDeck tables, authentication settings, or live n8n workflow configuration as a side effect of app work.
- Episode progress is distinct canonical episodes, even when multiple sources support a completion. Keep source evidence and manual overrides; exclude One Piece and Fairy Tail.
- Trakt watches and manual check-ins have dated activity. Historical Crunchyroll completions remain undated. Promptly observed Crunchyroll activity may show a **source-reported** date only under the documented observation policy in `docs/SOURCE_OF_TRUTH.md`. Never convert bulk backfill timestamps into watch dates.
- Run `npm test` and `npm run build` from `web/` before publishing app changes. Run relevant existing pipeline checks after SQL changes. Verify mobile layouts and data states against the deployed app, at iPhone width when feasible; a preview is optional under the workflow above.

## Shared skills

The vendored skills live under `.agents/skills/`; `.claude/skills/` links to the same files. Open the skill's `SKILL.md` for each relevant task:

| Skill | Use when |
| --- | --- |
| `interface-design` | Designing or refining product screens, hierarchy, navigation, or interaction states. |
| `react-best-practices` | Writing, reviewing, or refactoring React and client data loading. Apply React rules that fit this Vite app; Next.js rules apply only if that framework is introduced. |
| `web-design-guidelines` | Auditing UI and accessibility. It fetches current upstream guidance, so record which version was reviewed. |

Do not let a skill override the canonical ingestion rules or user decisions. Skill sources and pinned revisions are documented in `.agents/skills/README.md`.
