# Vigil v1 release verification

Release scope: freeze the established research interface, saved investigations, evidence drawer, period comparisons, 3D axes, and research briefs. Add deployment packaging and verification without removing existing views or tools.

## Verified on October 25, 2026

- Real FDA end-to-end browser workflow: autocomplete → applied metformin cohort → nausea evidence → matching case reports → save → reopen → update notes → two-revision timeline → research brief download.
- The reopened workspace and downloaded brief retain the applied drug/dates, exact reaction, counts, PRR/interval, saved notes, and both revisions. This used an isolated library, not personal saved investigations.
- Live January 2025 FDA smoke check: 2,172 reports, weekly total 2,172, 20 report samples, 50 reaction estimates, and 50 seriousness comparisons.
- Five live MAUDE narratives returned through the existing device-narrative path.
- All four live model variants trained on 300 reports, using 251 training and 49 held-out records with paired held-out labels across feature sets.
- Existing desktop/phone checks cover chart selection, rotation/reset, drawer behavior, timeline, contained horizontal chart/table scrolling, keyboard focus containment, Escape, and focus return.
- The production transport rejects unauthenticated access and unrecognized hosts/origins, bounds request bodies, retains notes/revisions across app recreation, and preserves the existing JSON/static/HEAD routes.

The build/test output and GitHub release checks are the final authority for the release commit. Container deployment must pass the CI build/restart smoke check, and the free hosted instance must pass its own post-deployment persistence check before being described as live and verified. Local Docker Desktop was installed but its Linux engine was unavailable during preparation; the Linux container job therefore checks the image and app-recreation persistence. PostgreSQL integration contracts run against an isolated database service in CI; they are skipped locally when no test database URL is configured.

## Stop condition

Once the release checks pass and the chosen deployment passes sign-in, the complete research workflow, and persistence through redeployment, call this **v1 complete**. Keep new features out of the release until actual use identifies a concrete need. No claim is made that all possible bugs or workloads have been tested.

## Known scope

- The selected free plan uses Render Free plus Neon Free PostgreSQL; local use retains SQLite. Free services may sleep or hit plan quotas.
- One owner library per hosted service, protected by a workspace credential; separate public visitor accounts are not implemented.
- Historical charts are not stored in revisions. Older libraries start at the last available save rather than inventing earlier history.
- Briefs capture loaded aggregate evidence and saved notes; HTML is the native download, with browser printing available for PDF.
- Live FDA availability and source limitations still apply. No fallback silently replaces a failed FDA query with synthetic data.
- The hosted app starts with an empty investigation library. Local investigations are not uploaded by the release.

See [deployment and recovery](DEPLOYMENT.md) and the [short walkthrough](DEMO.md).
