# Comfortable desktop layout verification

Verified locally on 2026-10-25 using the production build and an FDA cohort.

- 3840 × 2160: centered workspace is capped at 2,000 CSS pixels. The larger text and shorter hero remain; all four metrics sit directly above the charts.
- Subject drug, date range, source, Filters, and Apply stay grouped together, without automatic spacing pushing actions to the opposite edge.
- 390 × 844: no horizontal page overflow; mobile artwork, navigation, and all four metrics remain available. Metrics now follow the cohort controls and reaction focus.
- Frontend tests: 37 passed. Production build: passed.
- Backend calculations, storage, API behavior, and research tools are unchanged.

The earlier wider-layout pass also exercised the evidence drawer, Signals, Network, Case reports, and Narrative lab. These checks cover the listed paths and sizes, rather than guaranteeing the absence of every possible bug.

[4K preview](preview-wide-overview.png) · [Mobile preview](preview-mobile-overview.png)
