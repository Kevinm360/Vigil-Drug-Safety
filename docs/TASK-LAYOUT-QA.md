# Task-focused layout pass

## Saved version

Before editing, the clean UI at `e605a38` was saved with the annotated local tag `checkpoint-before-task-layout-20261025`. It preserves the prior palette, depth treatment, and 1,600-pixel workspace. To inspect that version without changing this branch:

```powershell
git switch -c codex/inspect-saved-ui checkpoint-before-task-layout-20261025
```

## Changes

- Overview retains its full artwork and data-card treatment. Other views use smaller animated headers, quieter status rows, and flat evidence sections.
- Lab retains the full cohort/source controls inside a keyboard-operable disclosure. Subject, dates, and source remain visible when collapsed. Investigation actions and connected reaction focus remain available above the task.
- Model studio groups the training design, sample-size selector, and primary action. Initial, training, ready, and failure messages distinguish state; an existing evaluation remains available during another run. Methodology and proxy audit remain intact.
- Narrative lab pairs the text editor with analysis methodology and the independent FDA device source. Analyze precedes Upload in both visual and keyboard order. Character/CSV counts, limits, busy messages, error messages, and source-specific empty states clarify the workflow.
- Lab input and setup remain available while cohort context loads, or if cohort retrieval fails. Backend errors stay explicit; this does not replace FDA data with synthetic results.
- Result headings separate input from evidence. ROC/PR captions state axis meanings and scales. Tables retain sorting, search, pagination, and raw CSV export; model metrics use three decimal places, reporting ratios two, and missing values remain distinct from zero. Sorted columns expose `aria-sort`.

## Verification

Checked on 2026-10-25:

- Production build passed; 38 frontend tests passed, including missing/zero values and small model-metric formatting.
- Seven backend NLP and serious-outcome integrity tests passed.
- At 1600 × 1100: inspected Overview, Model studio, Narrative lab, Reactions/Signals, Network, Case reports, and Severity. No page overflow on the inspected views.
- At 390 × 844: Model studio and Narrative lab fit without horizontal page overflow; narrative editor and device-source fields fit their containers.
- Cohort disclosure opens with Enter; Escape closes the filter dialog and returns focus to its Filters trigger.
- Synthetic example text analysis completed; progress feedback, keyword scores, sentiment, and annotated-record table appeared.
- Signal 3D mode, rotation/reset, reaction selection, and the evidence drawer worked after the layout change.
- Report search showed a specific empty-search explanation and recovered the table after clearing the query.
- A 300-report live model training request reached the backend and showed its busy state, then failed with an openFDA connectivity error. A successful live training run and its populated evaluation layout were therefore not verified in this pass. Existing calculation logic was not changed; failure/retry feedback is explicit.

These are bounded checks, not a guarantee that every possible bug is absent. No personal investigations were edited or deleted, and no deployment or push was performed.

[Model studio](preview-task-models.png) · [Narrative lab](preview-task-narratives.png) · [Mobile Model studio](preview-task-mobile.png)
