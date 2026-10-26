# Widescreen layout verification

Verified locally on 2026-10-25 using the production build and the live FDA cohort.

- 3840 × 2160: workspace expands to 2,800 CSS pixels; overview metrics sit alongside the shorter artwork panel; weekly chart and evidence brief fit side by side.
- 2560 × 1440: workspace expands to about 2,150 pixels; overview, Signals, Network, Case reports, and Narrative lab have no horizontal page overflow.
- 1440 × 900: workspace is about 1,338 pixels; metrics stack below the hero. Opening reaction evidence reduces the workspace to about 898 pixels and reflows charts into one column without page overflow.
- 390 × 844: overview remains within the viewport; the original mobile artwork, four navigation groups, and two-column metrics remain available.
- Selecting Nausea opens its evidence drawer with matching counts, PRR/ROR intervals, and connected report controls. Closing the drawer returns to the chart.
- Frontend tests: 37 passed. Production build: passed.

This pass changes layout and typography. Backend calculations, storage, APIs, and research tools are unchanged. These checks cover the listed paths and sizes, rather than guaranteeing the absence of every possible bug.

[4K preview](preview-wide-overview.png) · [Mobile preview](preview-mobile-overview.png)
