# Beatrice: first application slice

Approved direction: Noxian charcoal/crimson/brass, persistent Home/Draft/Team/History sidebar, multiple teams with one active selection, five fixed roles and no substitutes.

The initial slice implements team creation, renaming, roster editing, manually entered Riot IDs, and comfort (now 1–10). Home derives readiness from saved rosters. The champion/draft extension adds local catalog selection, both manual draft formats, and recorded results. See [the champion and draft guide](champions-and-drafts.md) for the current workflow and limitations. No match data or AI claims are invented.

Persistence uses Spring JDBC repositories and Flyway rather than JPA for this slice. Explicit SQL is easy to inspect and avoids entity lifecycle complexity. Controllers handle HTTP, services validate and transact, repositories persist. A later JPA adoption is possible without changing the API.

Database uniqueness protects team names regardless of case, even with simultaneous requests. Version checks prevent stale updates. Team updates and champion pool replacement are one transaction. Tests use disposable PostgreSQL through Testcontainers.

Next: player-to-pick assignments, Riot imports, evidence-based statistics and recommendations, then ML and conversational assistance. Champion catalog selection, manual draft sequencing, results, and a comfort-only shortlist are now implemented.

Learning map: TeamData defines JSON, TeamController maps HTTP, TeamService enforces rules, TeamRepository owns SQL, V1 migration defines constraints. Frontend api/teams.ts isolates requests, TeamEditor owns unsaved changes, App owns navigation and active-team selection.
