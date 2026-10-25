# Evidence drawer verification

Verified with the production bundle and local FDA-backed app on 2026-10-24.

- Production build succeeds; 23 frontend tests and 83 Python regression tests pass.
- Live Ibuprofen cohort (2025-06-18 through 2025-09-15): Fatigue 337, Nausea 284, Angioedema 306. Drawer counts agree with the reaction chart and exact-reaction report totals. Five preview records are shown from the retrieved 20-report sample; inspected Angioedema previews all contain that reaction.
- Bar, treemap, table, network, signal/3D, period comparison, and seriousness chart selections open the drawer. Treemap Enter, 3D Space, and forest Enter work. Tooltip handlers retain Escape behavior and no longer override reaction activation.
- Rapid reaction changes replace counts and record state; unit tests reject results keyed to another reaction/cohort, failed responses, mismatched terms, and incomplete responses. Missing statistics/counts stay unknown; real zero counts remain zero. Request cancellation is supported.
- Existing Chart/Treemap/Table, signal Co-occurrences/Volcano/3D, network controls, focused Case reports, grouped navigation, and period comparison remain available. Drawer shortcuts preserve the selected reaction and select the correct section. Closing the drawer preserves the reaction focus and chart mode.
- Existing saved notes open in the drawer. The notes action opens the original editor with its existing name/text, Update investigation, and Save as new. Inspection did not update or delete any saved investigation. Original backend revision and persistence regression tests pass.
- At 1440px the chart and drawer sit beside each other without page overflow. At 390px the drawer fits the viewport, the page is inert behind it, Tab/Shift+Tab remain inside, Escape closes it, and focus returns to Open evidence. Notes-editor handoff focuses Investigation name. Body scrolling is restored on close. The temporary viewport override was reset after testing.
- No browser console errors were recorded in the tested build.

The tests exercise frontend data/error contracts; an actual FDA outage was not induced. FDA requests remain subject to the existing availability, cache, and sample limits. No new backend endpoint, database, dependency, credential storage, or medical interpretation service was introduced.
