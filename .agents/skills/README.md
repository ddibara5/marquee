# Shared skill sources

These are project-local copies so agents working with this Git repository use the same guidance. The `.claude/skills/` entries are relative symlinks to these copies.

| Skill | Upstream | Pinned commit | License |
| --- | --- | --- | --- |
| `interface-design` | https://github.com/Dammyjay93/interface-design | `2f9be32` | MIT; license copied with skill |
| `react-best-practices` | https://github.com/vercel-labs/agent-skills | `063bee9` | MIT per skill frontmatter/upstream README |
| `web-design-guidelines` | https://github.com/vercel-labs/agent-skills | `063bee9` | MIT per upstream README |

Refresh vendored copies deliberately, check upstream terms and changes, and keep these pinned revisions current. `web-design-guidelines` fetches its rule text at review time from the URL in its `SKILL.md`.
