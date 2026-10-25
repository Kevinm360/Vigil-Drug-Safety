# Vigil v1 walkthrough

![Vigil investigation workflow](demo-v1.gif)

This short walkthrough is assembled from verified browser states, recorded on October 25, 2026. It uses an isolated investigation library and real FDA aggregate queries; it does not modify personal saved investigations.

1. Search **metf** in the subject-drug dropdown and select **Metformin**. Apply the cohort.
2. In **Explore → Reactions**, select **Nausea** to open its evidence drawer.
3. Follow **Case reports**. The exact reaction and applied cohort remain selected.
4. Save the investigation and its research notes. Reopen it from **Saved investigations**.
5. Update the notes, then open **Timeline & brief** to inspect both revisions.
6. Open **Research brief**, refresh the preview if needed, and download the self-contained HTML. It includes the same cohort, reaction, estimates, notes, and history. Use the browser's Print command to save a PDF.

The captured cohort is METFORMIN, January 2, 2024 through September 15, 2025, with all demographic/reporter filters. This captured run returned 43,541 subject-drug reports and 3,563 matching nausea reports. The reaction estimate was PRR 2.45, with a 95% interval of 2.37–2.53. The supporting records are a bounded sample of 20. These recorded values are not a promise about a later FDA query, and they do not establish incidence or causation.

The original Streamlit recording is still available in [reference/demo.gif](reference/demo.gif).
