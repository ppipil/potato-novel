## 1. Guest Access and Permission Boundaries

- [x] 1.1 Add guest-mode bookshelf entry so unauthenticated users are not redirected away from bookshelf.
- [x] 1.2 Introduce viewer-mode state (`guest` / `authenticated`) and propagate it to bookshelf and story result views.
- [x] 1.3 Enforce backend permission checks so ending-analysis requests require authenticated token context.
- [x] 1.4 Ensure guest-generated stories are never persisted to shared backend story storage.

## 2. Bookshelf Public/Mine Information Architecture

- [x] 2.1 Add `公共` and `我的` tabs to bookshelf and wire active-tab state.
- [x] 2.2 Bind public library stories to `公共` and personal story collections to `我的`.
- [x] 2.3 Ensure free-created stories are categorized into `我的` for both guest and authenticated modes.
- [x] 2.4 Add empty-state and explanatory copy for guest local-only personal shelf.

## 3. Prose-First Custom Generation Refactor

- [x] 3.1 Refactor story generation orchestration to hydrate each turn node in prose-first then choice-second order.
- [x] 3.2 Update choice prompt composition so it must consume generated node prose as context.
- [x] 3.3 Keep deterministic node iteration order and preserve package validation invariants.
- [x] 3.4 Add fallback/error handling for partial node generation failures without returning malformed packages.

## 4. Validation and Regression Coverage

- [ ] 4.1 Add integration checks for guest bookshelf access, guest custom creation, and guest local-only persistence behavior.
- [ ] 4.2 Add UI regression checks for tab visibility and story placement rules (`公共` vs `我的`).
- [ ] 4.3 Add generation-pipeline regression checks to verify prose is generated before choices for each turn node.
- [ ] 4.4 Add permission regression checks to verify ending-signature action is hidden in guest UI and rejected by API.

## 5. Choice Audio Feedback

- [x] 5.1 Add lightweight click sound playback for story choice buttons.
- [x] 5.2 Ensure sound playback is non-blocking and gracefully degrades when audio cannot autoplay or fails to load.
- [ ] 5.3 Add interaction regression checks to verify one-shot sound is triggered only on user choice click.
