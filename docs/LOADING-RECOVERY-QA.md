# Loading, recovery, and freshness verification

Verified on 2026-10-25 with the production bundle and local FDA-backed app.

- Production build succeeds. All 91 Python tests and 29 frontend tests pass.
- Independent requests load core cohort data first, then signals, severity/demographics, reports, and the optional drug comparison. Unit tests verify that signal retries omit report, seriousness, and comparison work and retain the same applied filters.
- With a live Ibuprofen investigation open, the local API was briefly stopped. Refreshing only Signal estimates displayed an explicit retained-result warning while keeping all 50 plotted points, 3D mode, ANGIOEDEMA focus, the saved investigation, and the unaffected core section. Restarting the API and pressing Retry recovered the signal section without a page reload. This was a local API connectivity test, not an induced FDA outage.
- Network search remained `nausea` after independently refreshing signals. The filtered relationship map remained visible. Case reports still displayed its retrieved records; all seven existing severity/demographic panels remained available.
- The saved 90-day comparison restored its dates and reaction focus. Its local Refresh comparison retained the `angioedema` table search and interval chart. FDA/cache retrieval details were verified for the comparison worker requests.
- Cache tests verify original retrieval timestamps and expiry across network, memory, SQLite reuse, a delayed cache write, and worker threads. No new cache window starts when an entry is reused. Existing privacy, cache-limit, API-origin, and investigation revision tests continue to pass.
- Frontend tests cover late errors from older cohorts, overlapping retries whose transport ignores cancellation, mismatched calculation bases, exact filter normalization, preserved comparison zeros/counts, and graph signal metadata. A changed calculation basis requests a cohort refresh rather than mixing denominators.
- At 390px, the expandable status list and individual refresh buttons fit without page overflow. A mobile signal refresh retained the current 3D chart while reporting loading. The viewport override was reset afterward.

The UI continues to use bounded samples and the existing FDA cache policy. Refresh reuses eligible unexpired responses; it does not guarantee a network request. Displayed last-successful snapshots are labeled after a failed refresh. Switching cohorts clears previous evidence. No existing chart, tab, export, filter, investigation, narrative, or model feature was removed.
