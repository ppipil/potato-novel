## 1. Reading Density And Layout Polish

- [ ] 1.1 Reduce oversized spacing and component scale in active reading choice dock while preserving tap usability.
- [ ] 1.2 Reduce bookshelf template card and composer visual footprint for faster scanning.
- [ ] 1.3 Tune typography and spacing rhythm to keep prose readability while increasing information density.

## 2. Loading And Failure Experience

- [ ] 2.1 Replace blocking generation overlay on bookshelf start flow with non-blocking in-page waiting feedback.
- [ ] 2.2 Add explicit timeout/network failure messages with actionable retry guidance.
- [ ] 2.3 Ensure generation states remain discoverable while users continue other browsing actions.

## 3. Story Flow Behavior Fixes

- [ ] 3.1 Implement deterministic auto-scroll triggers for node switch, reveal progression, and dock appearance.
- [ ] 3.2 Render `directorNote` as current-turn context instead of accumulating full-history note blocks.
- [ ] 3.3 Verify repeated multi-choice progression keeps scroll position behavior consistent.

## 4. Narrative Pacing Improvement

- [ ] 4.1 Increase prose depth requirements in node prompt constraints (normal and ending nodes).
- [ ] 4.2 Validate that generated nodes avoid abrupt short-form cutoffs in common paths.

## 5. Validation

- [ ] 5.1 Validate bookshelf experience on mobile viewport for scanning density and long-wait generation.
- [ ] 5.2 Validate interactive reading flow for header readability, note rendering, and auto-scroll reliability.
- [ ] 5.3 Validate custom generation timeout/failure copy in unstable network scenarios.
