## 1. Design System Foundation

- [x] 1.1 Add Tailwind and theme configuration for paper, ink, and accent tokens, serif/sans font roles, shared radii, and shadow presets.
- [x] 1.2 Load `Noto Serif SC` and establish shared global primitives for the paper shell, blurred glow layers, hidden scrollbars, and safe-area spacing.
- [x] 1.3 Define shared keyframes and utility classes for typing dots, chunk-in reveal, slide-up dock motion, and pressed-state scaling.

## 2. Landing And Bookshelf Rebuild

- [x] 2.1 Rebuild the landing/login page into the parchment-style branded composition while preserving the existing SecondMe login and authenticated-entry behavior.
- [x] 2.2 Rebuild the bookshelf header and shared page shell so the authenticated dashboard matches the mobile-framed reading device layout.
- [x] 2.3 Implement the horizontal "我的宇宙" shelf with book-like cards, hidden scrollbar behavior, title mask, and turn-count badge treatment.
- [x] 2.4 Implement the "自由创作" composer card and the stacked template card list with genre tag, serif title, clamp behavior, and visual accent markers.

## 3. Interactive Story Reading Experience

- [x] 3.1 Refactor the active story page into a single-column literary reading layout with frosted top bar and bottom-safe reading padding.
- [x] 3.2 Render AI prose as unboxed serif narrative blocks and active user choices as right-aligned paper bubbles with a styled "我：" prefix.
- [x] 3.3 Rebuild the bottom action dock with stacked recommendation buttons, pill-shaped custom input, and state-based submit or forced-ending affordances.
- [x] 3.4 Add waiting and reveal presentation for the interactive page, including typing dots, chunk-in entry, and slide-up dock behavior while preserving existing continuation logic.

## 4. Review Reading Experience

- [x] 4.1 Rebuild the saved-story review page into the same paper reading shell with centered title and quiet navigation affordances.
- [x] 4.2 Render read-only user actions as centered divider labels with dashed horizontal separators instead of active-play bubbles.
- [x] 4.3 Add any lightweight frontend normalization needed to map saved-story metadata or transcript structure into the new review presentation without changing backend contracts.

## 5. Validation

- [ ] 5.1 Verify the unauthenticated and authenticated root-page flows still enter the correct login or bookshelf path after the redesign.
- [ ] 5.2 Verify bookshelf interactions for horizontal shelf scrolling, custom opening entry, and recommended template selection on mobile-sized layouts.
- [ ] 5.3 Verify the interactive story flow for paragraph reveal, recommendation selection, custom input submission, waiting states, and save behavior.
- [ ] 5.4 Verify the saved-story review page for title display, readable long-form narrative layout, and centered user-action divider rendering.
