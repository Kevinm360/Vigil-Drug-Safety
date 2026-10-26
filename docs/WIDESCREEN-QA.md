# Comfortable desktop layout verification

Verified locally on 2026-10-25 using the production build and an FDA cohort.

- 3840 × 2160: centered workspace is capped at 2,000 CSS pixels. The larger text and shorter hero remain; all four metrics sit directly above the charts.
- Subject drug, date range, source, Filters, and Apply stay grouped together, without automatic spacing pushing actions to the opposite edge.
- 390 × 844: no horizontal page overflow; mobile artwork, navigation, and all four metrics remain available. Metrics now follow the cohort controls and reaction focus.
- Frontend tests: 37 passed. Production build: passed.
- Backend calculations, storage, API behavior, and research tools are unchanged.

The earlier wider-layout pass also exercised the evidence drawer, Signals, Network, Case reports, and Narrative lab. These checks cover the listed paths and sizes, rather than guaranteeing the absence of every possible bug.

[4K preview](preview-wide-overview.png) · [Mobile preview](preview-mobile-overview.png)

## Spacing and contrast refinement

The following CSS-only refinement was also checked on 2026-10-25:

- 2560 × 1440: hero measures about 288 pixels tall, with its heading, description, action, and animation control visible. Reaction focus fits in a 59-pixel row when no reaction is selected.
- 1440 × 900: selecting Nausea retains all five reaction actions and opens the evidence drawer; the focus area wraps without page overflow.
- 390 × 844: the drawer can be closed and reaction focus cleared; no horizontal page overflow. Functional labels use darker sage text while decorative artwork keeps its original colors.
- Production build passed. No data, API, or interaction logic changed.

[Refined overview preview](preview-refined-overview.png)


## Warm stone and teal palette

- Shared neutral surfaces, charcoal/slate text, and teal actions applied across navigation, filters, tables, dialogs, evidence drawer, and lab panels. Animated artwork and tab accent colors remain intact.
- Chart series use muted teal, lavender, and terracotta; no calculations or interactions changed.
- Contrast ratios: main text/page 11.54:1; secondary text/page 5.38:1; secondary text/control surface 5.11:1; primary button text/background 5.82:1. These are the specified color pairs, not a full accessibility audit.
- Visually inspected Overview, Explore, Reports, and Narrative lab on desktop, plus Overview at 390 × 844. No mobile page overflow or captured browser console errors.
- Frontend tests: 37 passed. Final production build: passed.

[Stone and teal preview](preview-stone-teal-overview.png)


## Narrower reading workspace

The latest approved layout caps the shared workspace at 1,600 pixels, superseding the earlier 2,000-pixel cap. Long explanatory text is limited to 65ch (or its existing shorter measure); the narrative input also has a 65ch maximum.

Verified at 2560 × 1440: main width 1,600 pixels, no horizontal page overflow, report table container retains overflow-x: auto. At 390 × 844, the narrative input fits within the screen and the page has no horizontal overflow. Production build passed. Palette, feature logic, and text sizes are unchanged.

[Narrower Narrative lab preview](preview-focused-narratives.png)
