# Web Dashboard Release Evidence

This document records the evidence required before an academic demonstration or
external release. It does not substitute for a manual review or usability study.

## Automated Checks

Run from `frontend/`:

```text
npm test
npm run typecheck
npm run build
```

Record the date, commit, output, and reviewer for each run. The production build
currently reports a non-blocking bundle-size warning for the Recharts bundle.

## Message Inventory

Review every user-facing Indonesian string in `frontend/src/App.tsx` and the API
contract against the approved copy in
`docs/web-dashboard-mvp-contract.md`. Confirm that each loading, pending, stale,
fallback, unavailable, partial-weather, retry, and no-data state has one visible
message and does not announce repeated countdown or background changes.

Reviewer: ____________________  Date: ____________________

## Critical-State Screenshots

Capture the release layout at desktop and mobile widths for:

- Normal prediction with `Tidak hujan` and `Sedang` preparation.
- Near-threshold prediction.
- Pending prediction.
- Stale prediction.
- Fallback prediction.
- Unavailable prediction.
- Partial Current Weather.
- Failed request with Retry.
- Empty and populated history.

Evidence location: ____________________

## Accessibility Review

Verify keyboard-only access, visible focus, heading and landmark structure, live
announcements, table/chart equivalence, contrast, zoom/reflow, and reduced motion.

Reviewer: ____________________  Date: ____________________
Findings and disposition: _________________________________________________

## Usability Check

Use ten representative first-time Decision Users on the release-relevant layout.
At least nine must identify both the Predicted Class and preparation action within
ten seconds without coaching. Include normal, near-threshold, stale, fallback,
unavailable, and valid `Tidak hujan` with `Sedang` preparation cases.

Result: ______ / 10 within ten seconds
Study date: ____________________  Facilitator: ____________________
Notes: ____________________________________________________________________

## Second Review

Reviewer: ____________________  Date: ____________________
Approval:  [ ] approved  [ ] changes required
Signature or issue link: _________________________________________________
